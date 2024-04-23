import asyncio
import io
import os
from contextlib import contextmanager
from typing import List

import deepdrr
from deepdrr import geo
from deepdrr.utils import test_utils, image_utils
from deepdrr.projector import Projector
from PIL import Image
import logging
from pathlib import Path
import numpy as np

import time


import capnp
import deepdrr
import numpy as np
import typer
import zmq.asyncio
from PIL import Image
from deepdrr import geo
from deepdrr.projector import Projector
from deepdrrzmq.utils import timer_util

from deepdrrzmq.devices import SimpleDevice
from deepdrrzmq.utils.zmq_util import zmq_no_linger_context, zmq_poll_latest

from .utils.drr_util import from_nifti_cached, from_meshes_cached
from .utils.typer_util import unwrap_typer_param
from .instruments.KWire450mm import KWire450mm

import pyvista as pv

from .utils.server_util import make_response, DeepDRRServerException, messages

# app = typer.Typer()
app = typer.Typer(pretty_exceptions_show_locals=False)

file_path = os.path.dirname(os.path.realpath(__file__))



def mesh_msg_to_volume(meshParams):
    """
    Convert a mesh message to a volume.

    :param meshParams: The mesh to convert.
    :return: The volume.
    """
    surfaces = []
    for volumeMesh in meshParams.meshes:
        vertices = np.array(volumeMesh.mesh.vertices).reshape(-1, 3) # Convert to Nx3 array
        faces = np.array(volumeMesh.mesh.faces).reshape(-1, 3) # Convert to Nx3 array
        faces = np.pad(faces, ((0, 0), (1, 0)), constant_values=3) # Add face count to front of each face
        faces = faces.flatten() # Flatten to 1D array
        if len(faces) == 0:
            continue
        surface = pv.PolyData(vertices, faces) # Create pyvista surface
        surfaces.append((volumeMesh.material, volumeMesh.density, surface)) # Add surface to list of surfaces

    # Create volume from surfaces
    meshVolume = from_meshes_cached(
        voxel_size=meshParams.voxelSize,
        surfaces=surfaces
    )
    return meshVolume

def nifti_msg_to_volume(niftiParams, patient_data_dir):
    """
    Convert a nifti message to a volume.

    :param niftiParams: The nifti message to convert.
    :param patient_data_dir: The directory containing the patient data.
    :return: The volume.
    """

    # if niftiParams.path is a relative path, make it relative to the patient data directory
    niftiParamsPath = Path(niftiParams.path)
    if not niftiParamsPath.expanduser().is_absolute():
        niftiWildcardsPath = patient_data_dir / niftiParamsPath
    else:
        niftiWildcardsPath = niftiParamsPath
        
    niftiCaseDir = niftiWildcardsPath.parent
    niftiVolumeName = niftiWildcardsPath.name
    niftiPaths = sorted(niftiCaseDir.glob(niftiVolumeName)) + [niftiWildcardsPath]
    niftiPath = str(niftiPaths[0])
    print(f"niftiPath [{type(niftiPath)}]: {niftiPath}")

    niftiVolume = from_nifti_cached(
        path=niftiPath,
        world_from_anatomical=capnp_square_matrix(niftiParams.worldFromAnatomical),
        use_thresholding=niftiParams.useThresholding,
        use_cached=niftiParams.useCached,
        save_cache=niftiParams.saveCache,
        cache_dir=capnp_optional(niftiParams.cacheDir),
        # materials=None,
        segmentation=niftiParams.segmentation,
        # density_kwargs=None,
    )
    return niftiVolume


def capnp_optional(optional):
    """
    Convert a capnp optional to a python optional.
    
    :param optional: The capnp optional.
    :return: The python optional.
    """
    if optional.which() == "value":
        return optional.value
    else:
        return None

def capnp_square_matrix(optional):
    """
    Convert a capnp optional square matrix to a numpy array.
    
    :param optional: The capnp optional square matrix.
    :return: The numpy array.
    """
    if len(optional.data) == 0:
        return None
    else:
        arr = np.array(optional.data)
        size = len(arr) # number of elements
        side = int(size ** 0.5) # square root
        assert size == side ** 2, f"expected square matrix, got {size} elements"
        arr = arr.reshape((side, side))
        return arr

class DeepDRRServer:
    """
    DeepDRR server that handles requests from the client and sends responses.

    The server is implemented as a single asyncio task that runs forever.

    The server is responsible for:
    - handling requests from the client
    - sending responses to the client
    - managing the projector
    - managing the volumes
    """
    def __init__(self, context, rep_port, pub_port, sub_port):
        """
        Create a new DeepDRR server.
        
        :param context: The zmq context.
        :param rep_port: The port to use for the request-reply socket.
        :param pub_port: The port to use for the publish socket.
        :param sub_port: The port to use for the subscribe socket.
        """
        self.context = context
        self.rep_port = rep_port
        self.pub_port = pub_port
        self.sub_port = sub_port

        self.disable_until = 0

        self.projector = None
        self.projector_id = ""
        self.projector_loading = False

        self.volumes = []  # type: List[deepdrr.Volume]

        self.fps = timer_util.FPS(1) # FPS counter for projector
        
        self.priority_request_queue = []    # queue for priority requests
        
        # PATIENT_DATA_DIR environment variable is set by the docker container
        # patient_data_dir_default = Path("/mnt/d/jhonedrive/Johns Hopkins/Benjamin D. Killeen - NMDID-ARCADE/")  # TODO: remove
        # patient_data_dir_default = Path("/nfs/centipede/liam/OneDrive/NMDID-ARCADE")
        patient_data_dir_default = Path("/home/virtualpelvislab/datasets/NMDID-ARCADE")
        self.patient_data_dir = Path(os.environ.get("PATIENT_DATA_DIR", patient_data_dir_default))
        print(f"patient data dir: {self.patient_data_dir}")
        logging.info(f"patient data dir: {self.patient_data_dir}")

    async def start(self):
        """
        Start the server.
        """

        project = self.project_server()
        status_loop = self.status_server()
        await asyncio.gather(project, status_loop)

    async def project_server(self):
        """
        Project server that handles requests from the client and sends responses.
        """
        sub_socket = self.context.socket(zmq.SUB)
        sub_socket.hwm = 10000

        pub_socket = self.context.socket(zmq.PUB)
        pub_socket.hwm = 10000

        pub_socket.connect(f"tcp://localhost:{self.pub_port}")
        sub_socket.connect(f"tcp://localhost:{self.sub_port}")

        sub_socket.setsockopt(zmq.SUBSCRIBE, b"/priority_project_request/")
        sub_socket.setsockopt(zmq.SUBSCRIBE, b"/project_request/")
        sub_socket.setsockopt(zmq.SUBSCRIBE, b"/projector_params_response/")
        sub_socket.setsockopt(zmq.SUBSCRIBE, b"/deepdrrd/in/")

        while True:

            try:
                no_drop_topics = [b"/priority_project_request/"]
                latest_msgs = await zmq_poll_latest(sub_socket, no_drop_topics=no_drop_topics)

                if b"/deepdrrd/in/block/" in latest_msgs:
                    self.disable_until = time.time() + 10

                if time.time() < self.disable_until:
                    await asyncio.sleep(1)
                    print("deepdrrd disabled")
                    continue

                if b"/projector_params_response/" in latest_msgs:
                    try:
                        await self.handle_projector_params_response(pub_socket, latest_msgs[b"/projector_params_response/"])
                    except Exception as e:
                        raise DeepDRRServerException(1, f"error creating projector", e)

                # handle queued priority requests
                if self.priority_request_queue:
                    request = self.priority_request_queue.pop(0)
                    await self.handle_project_request(pub_socket, request, priority=True)
                else:
                    if b"/priority_project_request/" in latest_msgs:
                        await self.handle_project_request(pub_socket, latest_msgs[b"/priority_project_request/"], priority=True)

                    if b"/project_request/" in latest_msgs:
                        if await self.handle_project_request(pub_socket, latest_msgs[b"/project_request/"]):
                            if (f:=self.fps()) is not None:
                                print(f"DRR project rate: {f:>5.2f} frames per second")
                
                # allow send_status heartbeat to run
                await asyncio.sleep(0)

            except DeepDRRServerException as e:
                print(f"server exception: {e}")
                if e.subexception is not None:
                    logging.exception(e.subexception)
                await pub_socket.send_multipart([b"/server_exception/", e.status_response().to_bytes()])


    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.projector is not None:
            self.projector.__exit__(exc_type, exc_value, traceback)

    async def handle_projector_params_response(self, pub_socket, data):
        """
        Handle a projector params response from the client.
        
        :param data: The data of the response.
        """
        # for now, only one projector at a time
        # if the current projector is not the same as the one in the request, delete the old and create a new one
        with messages.ProjectorParamsResponse.from_bytes(data) as command:
            if self.projector_id == command.projectorId:
                return
            
            if self.projector is not None:
                self.projector.__exit__(None, None, None)
            
            self.projector = None
            self.projector_id = command.projectorId
            self.projector_loading = True
                
            await self.send_status(pub_socket)
            
            print(f"creating projector {command.projectorId}")

            projectorParams = command.projectorParams

            # create the volumes
            self.volumes = []
            for volumeParams in projectorParams.volumes:
                print(f"adding {volumeParams.which()} volume")
                if volumeParams.which() == "nifti":
                    self.volumes.append(nifti_msg_to_volume(volumeParams.nifti, self.patient_data_dir))
                elif volumeParams.which() == "mesh":
                    self.volumes.append(mesh_msg_to_volume(volumeParams.mesh))
                elif volumeParams.which() == "instrument":
                    instrumentParams = volumeParams.instrument
                    known_instruments = {
                        "KWire450mm": lambda: KWire450mm(
                            density=instrumentParams.density,
                            world_from_anatomical=capnp_square_matrix(instrumentParams.worldFromAnatomical),
                        ),
                    }
                    if instrumentParams.type not in known_instruments:
                        raise DeepDRRServerException(1, f"unknown instrument: {instrumentParams.type}")
                    instrumentVolume = known_instruments[instrumentParams.type]()
                    self.volumes.append(
                        instrumentVolume
                    )
                else:
                    raise DeepDRRServerException(1, f"unknown volume type: {volumeParams.which()}")
            
            # create the projector
            print(f"creating projector")
            deviceParams = projectorParams.device
            device = SimpleDevice(
                sensor_height=deviceParams.camera.intrinsic.sensorHeight,
                sensor_width=deviceParams.camera.intrinsic.sensorWidth,
                pixel_size=deviceParams.camera.intrinsic.pixelSize,
                source_to_detector_distance=deviceParams.camera.intrinsic.sourceToDetectorDistance,
                world_from_device=geo.frame_transform(capnp_square_matrix(deviceParams.camera.extrinsic)),
            )            

            self.projector = Projector(
                volume=self.volumes,
                device=device,
                step=projectorParams.step,
                mode=projectorParams.mode,
                spectrum=projectorParams.spectrum,
                scatter_num=projectorParams.scatterNum,
                add_noise=projectorParams.addNoise,
                photon_count=projectorParams.photonCount,
                threads=projectorParams.threads,
                max_block_index=projectorParams.maxBlockIndex,
                collected_energy=projectorParams.collectedEnergy,
                neglog=projectorParams.neglog,
                intensity_upper_bound=capnp_optional(projectorParams.intensityUpperBound),
                attenuate_outside_volume=projectorParams.attenuateOutsideVolume,
            )
            self.projector.__enter__()

            print(f"created projector {self.projector_id}")
            self.projector_loading = False

    async def handle_project_request(self, pub_socket, data, priority=False):
        """
        Handle a project request from the client.

        :param pub_socket: The socket to send the response on.
        :param data: The data of the request.
        :param priority: Whether this is a priority request.
        """

        project_response_topic = b"/priority_project_response/" if priority else b"/project_response/"

        with messages.ProjectRequest.from_bytes(data) as request:

            # If the projector is not initialized or the projector id is mismatched,
            # send a response with a loading image and request the projector params
            if self.projector is None or request.projectorId != self.projector_id:                
                # send a response with a loading image
                msg = messages.ProjectResponse.new_message()
                msg.requestId = "__projector_loading__"
                msg.projectorId = request.projectorId
                msg.status = make_response(0, "ok")

                msg.init("images", 1)

                loading_img = np.zeros((512, 512, 3), dtype=np.uint8) # black
                pil_img = Image.fromarray(loading_img)
                buffer = io.BytesIO()
                pil_img.save(buffer, format="JPEG")
                msg.images[0].data = buffer.getvalue()
                
                await pub_socket.send_multipart([project_response_topic, msg.to_bytes()])

                # request the projector params
                msg = messages.ProjectorParamsRequest.new_message()
                msg.projectorId = request.projectorId
                await pub_socket.send_multipart([b"/projector_params_request/", msg.to_bytes()])
                print(f"projector {request.projectorId} not found, requesting projector params")
                
                # check if this is a priority request
                if priority:
                    self.priority_request_queue.append(data)
                
                return False

            # create the camera projections
            camera_projections = []
            for camera_projection_struct in request.cameraProjections:
                camera_projections.append(
                    geo.CameraProjection(
                        intrinsic=geo.CameraIntrinsicTransform.from_sizes(
                            sensor_size=(camera_projection_struct.intrinsic.sensorWidth, camera_projection_struct.intrinsic.sensorHeight),
                            pixel_size=camera_projection_struct.intrinsic.pixelSize,
                            source_to_detector_distance=camera_projection_struct.intrinsic.sourceToDetectorDistance,
                        ),
                        extrinsic=geo.frame_transform(capnp_square_matrix(camera_projection_struct.extrinsic))
                    )
                )

            # set the world from anatomical transforms
            volumes_world_from_anatomical = []
            for transform in request.volumesWorldFromAnatomical:
                volumes_world_from_anatomical.append(
                    geo.frame_transform(capnp_square_matrix(transform))
                )

            if len(volumes_world_from_anatomical) == 0:
                pass  # all volumes are static
            elif len(volumes_world_from_anatomical) == len(self.volumes):
                for volume, transform in zip(self.volumes, volumes_world_from_anatomical):
                    volume.world_from_anatomical = transform
            else:
                raise DeepDRRServerException(3, "volumes_world_from_anatomical length mismatch")

            # run the projector
            raw_images = self.projector.project(
                *camera_projections,
            )

            # if there is only one image, wrap it in a list
            if len(camera_projections) == 1:
                raw_images = [raw_images]

            # send the response
            msg = messages.ProjectResponse.new_message()
            msg.requestId = request.requestId
            msg.projectorId = request.projectorId
            msg.status = make_response(0, "ok")

            msg.init("images", len(raw_images))

            for i, raw_image in enumerate(raw_images):
                # use jpeg compression
                pil_img = Image.fromarray(((1-raw_image) * 255).astype(np.uint8))
                buffer = io.BytesIO()
                pil_img.save(buffer, format="JPEG")

                msg.images[i].data = buffer.getvalue()

            await pub_socket.send_multipart([project_response_topic, msg.to_bytes()])

            return True
        
    async def status_server(self):
        """
        Server for sending the status of the DRR projector.
        """
        pub_socket = self.context.socket(zmq.PUB)
        pub_socket.hwm = 10000

        pub_socket.connect(f"tcp://localhost:{self.pub_port}")

        while True:
            await asyncio.sleep(1)
            await self.send_status(pub_socket)
            
    async def send_status(self, pub_socket):
        """
        Send the status of the DRR projector.
        
        :param pub_socket: The socket to send the status on.
        """
        msg = messages.ProjectorHeartbeat.new_message()
        # "NoProjector", "Loading", "Loaded"
        if self.projector_loading:
            msg.status = "Loading"
        elif self.projector is None:
            msg.status = "NoProjector"
        else:
            msg.status = "Loaded"
        msg.projectorId = self.projector_id
        await pub_socket.send_multipart([b"/projector_heartbeat/", msg.to_bytes()])
    


@app.command()
@unwrap_typer_param
def main(
        rep_port=typer.Argument(40120),
        pub_port=typer.Argument(40121),
        sub_port=typer.Argument(40122),
):
    print(f"rep_port: {rep_port}")
    print(f"pub_port: {pub_port}")
    print(f"sub_port: {sub_port}")

    with zmq_no_linger_context(zmq.asyncio.Context()) as context:
        with DeepDRRServer(context, rep_port, pub_port, sub_port) as deepdrr_server:
            asyncio.run(deepdrr_server.start())


if __name__ == '__main__':
    app()

