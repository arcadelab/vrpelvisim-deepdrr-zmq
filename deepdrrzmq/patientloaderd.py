import asyncio
import json
import os

import logging
from pathlib import Path
import numpy as np

import capnp
import deepdrr
import numpy as np
import typer
import zmq.asyncio

from deepdrr.utils.mesh_utils import polydata_to_trimesh
from trimesh.repair import fill_holes, fix_normals
import pymeshfix as mf
import pyvista as pv

import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))
from deepdrrzmq.utils.zmq_util import zmq_no_linger_context
from deepdrrzmq.utils.typer_util import unwrap_typer_param
from deepdrrzmq.utils.server_util import make_response, DeepDRRServerException, messages, capnp_square_matrix, capnp_optional
import time

app = typer.Typer(pretty_exceptions_show_locals=False)


class PatientLoaderServer:
    """
    This class implements a server that can be used to load patient data.
    The server is used to load data from the patient loader service. It
    uses the ZeroMQ REQ/REP pattern to handle requests from the client.
    """
    def __init__(self, context, rep_port, pub_port, sub_port):
        """
        :param context: The ZMQ context to use for creating sockets.
        :param rep_port: The port to use for the request/reply socket.
        :param pub_port: The port to use for the publisher socket.
        :param sub_port: The port to use for the subscriber socket.
        """
        self.context = context
        self.rep_port = rep_port
        self.pub_port = pub_port
        self.sub_port = sub_port

        # PATIENT_DATA_DIR environment variable is set by the docker container
        patient_data_dir_default = Path("/nfs/centipede/liam/OneDrive/NMDID-ARCADE")
        self.patient_data_dir = Path(os.environ.get("PATIENT_DATA_DIR", patient_data_dir_default))
        logging.info(f"patient_data_dir: {self.patient_data_dir}")

    async def start(self):
        project = self.project_server()
        await asyncio.gather(project)

    async def project_server(self):
        sub_socket = self.context.socket(zmq.SUB)
        sub_socket.hwm = 10000

        pub_socket = self.context.socket(zmq.PUB)
        pub_socket.hwm = 10000

        pub_socket.connect(f"tcp://localhost:{self.pub_port}")
        sub_socket.connect(f"tcp://localhost:{self.sub_port}")

        sub_socket.setsockopt(zmq.SUBSCRIBE, b"/patient_mesh_request/")
        sub_socket.setsockopt(zmq.SUBSCRIBE, b"/patient_anno_request/")

        while True:
            try:
                latest_msgs = {}

                topic, data = await sub_socket.recv_multipart()
                latest_msgs[topic] = data

                # process all most recent messages received since the last time we checked
                for topic, data in latest_msgs.items():
                    if topic == b"/patient_mesh_request/":
                        await self.handle_patient_mesh_request(pub_socket, data)
                    elif topic == b"/patient_anno_request/":
                        await self.handle_patient_annotation_request(pub_socket, data)

            except DeepDRRServerException as e:
                print(f"server exception: {e}")
                await pub_socket.send_multipart([b"/server_exception/", e.status_response().to_bytes()])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    async def handle_patient_mesh_request(self, pub_socket, data):
        """
        Handle a patient mesh request. This method is called when a message is received on the
        patient_mesh_request topic. The message is parsed and the mesh is loaded from the
        patient data directory. The mesh is then sent back to the client on the patient_mesh_response
        topic.

        :param pub_socket: The publisher socket to use for sending the response.
        :param data: The message data.
        """
        with messages.MeshRequest.from_bytes(data) as request:
            print(f"patient_mesh_request: {request.meshId}")

            meshId = request.meshId
            mesh_file = self.patient_data_dir / meshId
            
            # parse mesh using pyvista
            try:
                mesh = pv.read(mesh_file)
            except Exception as e:
                print(f"patient_mesh_request error: {e}: {request.meshId}")
                return
                     
            # smooth mesh using pyvista
            taubin_smooth_iter = 50
            taubin_smooth_pass_band = 0.05
            mesh = mesh.smooth_taubin(n_iter=taubin_smooth_iter, pass_band=taubin_smooth_pass_band)

            # decimate mesh using pyvista
            decimation_points = 5000
            if mesh.n_points > decimation_points:
                # Decimate the surface to the desired number of points
                mesh = mesh.decimate(1 - decimation_points / mesh.n_points)
            
            # apply a triangle filter using pyvista to ensure the mesh is simply polyhedral
            mesh = mesh.triangulate()
            
            # fill holes using pymeshfix
            pymeshfix_ = mf.MeshFix(mesh)
            pymeshfix_.repair(verbose=True)
            mesh = pymeshfix_.mesh
            
            # fix winding order using trimesh
            trimesh_ = polydata_to_trimesh(mesh)
            fix_normals(trimesh_)
            mesh = pv.wrap(trimesh_)

            # create the response message
            msg = messages.MeshResponse.new_message()
            msg.meshId = meshId
            msg.status = make_response(0, "ok")
            msg.mesh.vertices = mesh.points.flatten().tolist()
            
            # flip winding order to match clinet's (Unity) convension
            msg.mesh.faces = mesh.faces.reshape((-1, 4))[..., 1:][..., [0, 2, 1]].flatten().tolist()

            response_topic = f"/patient_mesh_response/{meshId}"

            await pub_socket.send_multipart([response_topic.encode(), msg.to_bytes()])
            print(f"sent mesh response {response_topic}")


    async def handle_patient_annotation_request(self, pub_socket, data):
        """
        Handle a patient annotation request. This method is called when a message is received on the
        patient_anno_request topic. The message is parsed and the annotation is loaded from the
        patient data directory. The annotation is then sent back to the client on the patient_anno_response
        topic.
        
        :param pub_socket: The publisher socket to use for sending the response.
        :param data: The message data.
        """
        with messages.AnnoRequest.from_bytes(data) as request:
            print(f"patient_anno_request: {request.annoId}")

            annoId = request.annoId
            annotation_file = self.patient_data_dir / annoId

            # parse anno
            try:
                with open(annotation_file, "r") as f:
                    annotation = json.load(f)
            except Exception as e:
                print(f"patient_anno_request error: {e}: {request.annoId}")
                return

            # get the control points
            controlPoints = annotation["markups"][0]["controlPoints"]

            # create the response message
            msg = messages.AnnoResponse.new_message()
            msg.annoId = annoId
            msg.status = make_response(0, "ok")
            msg.anno.init("controlPoints", len(controlPoints))
            annoType = annotation["markups"][0]["type"]
            msg.anno.type = annoType

            for i, controlPoint in enumerate(controlPoints):
                msg.anno.controlPoints[i].position.data = controlPoint["position"]

            response_topic = f"/patient_anno_response/{annoId}"

            await pub_socket.send_multipart([response_topic.encode(), msg.to_bytes()])
            print(f"sent annotation response {response_topic}")
            


@app.command()
@unwrap_typer_param
def main(
        # ip=typer.Argument('localhost', help="ip address of the receiver"),
        rep_port=typer.Argument(40120),
        pub_port=typer.Argument(40121),
        sub_port=typer.Argument(40122),
        # bind=typer.Option(True, help="bind to the port instead of connecting to it"),
):

    # print arguments
    print(f"rep_port: {rep_port}")
    print(f"pub_port: {pub_port}")
    print(f"sub_port: {sub_port}")

    with zmq_no_linger_context(zmq.asyncio.Context()) as context:
        with PatientLoaderServer(context, rep_port, pub_port, sub_port) as patient_loader_server:
            asyncio.run(patient_loader_server.start())


if __name__ == '__main__':
    app()

