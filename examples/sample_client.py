import asyncio
import io
import math
import os
import random
import threading
import time
from contextlib import contextmanager
from typing import List
import asyncio

import capnp
import numpy as np
import typer
import zmq.asyncio
from PIL import Image

from deepdrrzmq.utils.zmq_util import zmq_no_linger_context
import cv2

from scipy.spatial.transform import Rotation as R



app = typer.Typer()

file_path = os.path.dirname(os.path.realpath(__file__))
messages = capnp.load(os.path.join(file_path, 'messages.capnp'))

resolution = 500
pixelSize = 1

projector_id = "test2"

async def start():
    receiver = receive_loop()
    requester = request_loop()
    await asyncio.gather(requester, receiver)

async def request_loop():
    speed = 0.1
    scale = 30

    # og_matrix = np.array(
    #     [[0, -1, 0, -1.95599373],
    #     [1, 0, 0, -1293.28274],
    #     [0, 0, 1, 829.996703],
    #     [0, 0, 0, 1]],
    # )

    og_matrix = np.array([
        [1, 0, 0, 0],
        [0, 1, 0, 0],
        [0, 0, 1, 1000],
        [0, 0, 0, 1]
    ],)

    rotspeed = 2




    while True:
        project_request = messages.ProjectRequest.new_message()

        project_request.requestId = "asdf"
        project_request.projectorId = projector_id
        project_request.init('cameraProjections', 1)
        project_request.cameraProjections[0].extrinsic.init('data', 16)

        matrix = og_matrix.copy()
        # matrix = np.eye(4)
        # matrix[1, 3] = 0
        # matrix[2, 3] = 0

        r = R.from_rotvec(math.sin(time.time() * rotspeed) * np.array([1, 0, 0]))

        # to homogeneous
        r_hom = np.eye(4)
        r_hom[:3, :3] = r.as_matrix()

        # matrix =  matrix @ r_hom
        # matrix = r_hom @ matrix

        # matrix[1, 3] += math.sin(time.time() * speed * 2 * math.pi) * scale


        for i in range(16):
            project_request.cameraProjections[0].extrinsic.data[i] = float(matrix[i // 4, i % 4])
            project_request.cameraProjections[0].intrinsic.sensorWidth = resolution
            project_request.cameraProjections[0].intrinsic.sensorHeight = resolution
            project_request.cameraProjections[0].intrinsic.pixelSize = pixelSize

        await pub_socket.send_multipart([b"project_request/", project_request.to_bytes()])

        # print(f"sending: {project_request}")

        await asyncio.sleep(0.01)
        # await asyncio.sleep(1)

async def receive_loop():
    while True:
        # print("waiting for next image...")
        topic, data = await sub_socket.recv_multipart()
        # print(f"received: {topic}")
        if topic == b"/project_response/":
            with messages.ProjectResponse.from_bytes(data) as response:
                # print(f"received image!")
                for img in response.images:
                    data = img.data
                    # read jpeg bytes
                    img = Image.open(io.BytesIO(data))
                    # print(img.size)
                    # show with opencv
                    cv2.imshow("image", np.array(img))
                    cv2.waitKey(1)
        elif topic == b"/projector_params_request/":
            with messages.StatusResponse.from_bytes(data) as response:
                # request a new projector
                msg = messages.ProjectorParamsResponse.new_message()
                msg.projectorId = projector_id
                msg.projectorParams.init("volumes", 1)
                msg.projectorParams.volumes[0].nifti.path = "/mnt/d/jhonedrive/Johns Hopkins/Benjamin D. Killeen - NMDID-ARCADE/nifti/THIN_BONE_TORSO/case-100114/THIN_BONE_TORSO_STANDARD_TORSO_Thorax_65008_11.nii.gz"
                # msg.projectorParams.volumes[0].nifti.path = "~/datasets/DeepDRR_Data/CTPelvic1K_dataset6_CLINIC_0001/dataset6_CLINIC_0001_data.nii.gz"
                msg.projectorParams.volumes[0].nifti.useThresholding = True
            with messages.ProjectorParamsRequest.from_bytes(data) as request:
                if request.projectorId == "test":
                    # request a new projector
                    msg = messages.ProjectorParamsResponse.new_message()
                    msg.projectorId = "test"
                    msg.projectorParams.init("volumes", 1)
                    msg.projectorParams.volumes[0].nifti.path = "~/datasets/DeepDRR_Data/CTPelvic1K_dataset6_CLINIC_0001/dataset6_CLINIC_0001_data.nii.gz"
                    msg.projectorParams.volumes[0].nifti.useThresholding = True

                    msg.projectorParams.device.camera.intrinsic.sensorWidth = resolution
                    msg.projectorParams.device.camera.intrinsic.sensorHeight = resolution
                    msg.projectorParams.device.camera.intrinsic.pixelSize = pixelSize
                    msg.projectorParams.threads = 16
                    msg.projectorParams.photonCount = 10
                    msg.projectorParams.step = 4
                    msg.projectorParams.device.camera.intrinsic.sensorWidth = resolution
                    msg.projectorParams.device.camera.intrinsic.sensorHeight = resolution
                    msg.projectorParams.device.camera.intrinsic.pixelSize = pixelSize
                    msg.projectorParams.threads = 16
                    msg.projectorParams.photonCount = 10
                    msg.projectorParams.step = 2

                    await pub_socket.send_multipart([b"projector_params_response/", msg.to_bytes()])
        else:
            print(f"unknown topic: {topic}")


@app.command()
def main(
        ip=typer.Argument('localhost', help="ip address of the server"),
        rep_port=typer.Argument(40120),
        pub_port=typer.Argument(40122),
        sub_port=typer.Argument(40121),
        # bind=typer.Option(True, help="bind to the port instead of connecting to it"),
):

    # print arguments
    print(f"req_port: {rep_port}")
    print(f"pub_port: {pub_port}")
    print(f"sub_port: {sub_port}")

    with zmq_no_linger_context(zmq.asyncio.Context()) as context:
        global pub_socket, sub_socket, req_socket

        req_socket = context.socket(zmq.REQ)
        req_socket.connect(f"tcp://{ip}:{rep_port}")

        pub_socket = context.socket(zmq.PUB)
        pub_socket.connect(f"tcp://{ip}:{pub_port}")

        sub_socket = context.socket(zmq.SUB)
        sub_socket.connect(f"tcp://{ip}:{sub_port}")

        sub_socket.setsockopt(zmq.SUBSCRIBE, b"")

        asyncio.run(start())


        # # send the request
        # req_socket.send(msg.to_bytes())
        # print("sent request")

        # # wait for the response
        # print("waiting for response")
        # response = req_socket.recv()
        # print("received response")

        # with messages.StatusResponse.from_bytes(response) as response:
        #     print(response)
        #     if response.code != 0:
        #         print("server returned error")
        #         return










if __name__ == '__main__':
    try:
        app()
    except KeyboardInterrupt:
        pass
    print("Exiting...")
