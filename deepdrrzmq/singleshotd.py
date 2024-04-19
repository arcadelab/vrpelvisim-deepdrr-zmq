import asyncio
import os

import logging
from pathlib import Path

import capnp
import typer
import zmq.asyncio
import time
from deepdrrzmq.utils.zmq_util import zmq_no_linger_context, zmq_poll_latest

from .utils.typer_util import unwrap_typer_param
from .utils.server_util import make_response, DeepDRRServerException, messages
import random
import string


import base64 
from PIL import Image
from io import BytesIO
import json


# app = typer.Typer()
app = typer.Typer(pretty_exceptions_show_locals=False)


class SingleShotServer:
    """
    Server for logging data from the surgical simulation.
    """
    def __init__(self, context, rep_port, pub_port, sub_port, log_root_path):
        """
        :param context: The zmq context to use.
        :param rep_port: The port to use for the request-reply socket.
        :param pub_port: The port to use for the publish socket.
        :param sub_port: The port to use for the subscribe socket.
        :param log_root_path: The path to the root folder where the logs should be stored.
        """
        self.context = context
        self.rep_port = rep_port
        self.pub_port = pub_port
        self.sub_port = sub_port
        self.log_root_path = log_root_path
        self.log_root_path.mkdir(parents=True, exist_ok=True)

    async def start(self):
        recorder_loop = self.logger_server()
        await asyncio.gather(recorder_loop)

    async def logger_server(self):
        """
        Server for logging data from the surgical simulation.
        """
        sub_socket = self.context.socket(zmq.SUB)
        sub_socket.hwm = 10000

        pub_socket = self.context.socket(zmq.PUB)
        pub_socket.hwm = 10000

        pub_socket.connect(f"tcp://localhost:{self.pub_port}")
        sub_socket.connect(f"tcp://localhost:{self.sub_port}")

        sub_socket.subscribe(b"/single_shot_request/")
        sub_socket.subscribe(b"project_request/")
        sub_socket.subscribe(b"/project_response/")
        
        requestId = None
        single_shot_request = None
        project_request = None
        project_response = None
        while True:
            try:
                latest_msgs = await zmq_poll_latest(sub_socket)

                for topic, data in latest_msgs.items():
                    
                    # this might not come first
                    if topic.startswith(b"/single_shot_request/"):
                        with messages.SingleShotRequest.from_bytes(data) as request:
                            requestId = request.requestId
                            single_shot_request = data
                            project_request = None
                            project_response = None
                        print(f"single shot request: {topic}")

                    if topic.startswith(b"project_request/"):
                        with messages.ProjectRequest.from_bytes(data) as request:
                            if request.requestId == requestId:
                                project_request = data
                    
                    if topic.startswith(b"/project_response/"):
                        with messages.ProjectResponse.from_bytes(data) as response:
                            if response.requestId == requestId:
                                project_response = data

                    if single_shot_request and project_request and project_response:
                        msgdict = {}
                        with messages.SingleShotRequest.from_bytes(single_shot_request) as request:
                            msgdict['requestId'] = request.requestId
                            msgdict['userId'] = request.userId
                            msgdict['patientCaseId'] = request.patientCaseId
                            msgdict['standardViewName'] = request.standardViewName
                        with messages.ProjectRequest.from_bytes(project_request) as request:
                            msgdict['projectorId'] = request.projectorId
                            cameraProjections_dict_ = []
                            for i in range(len(request.cameraProjections)):
                                current_cameraProjections = request.cameraProjections[i]
                                cameraProjections_dict = {}
                                camerainstrinsic_dict = {}
                                camerainstrinsic_dict['sensorHeight'] = current_cameraProjections.intrinsic.sensorHeight
                                camerainstrinsic_dict['sensorWidth'] = current_cameraProjections.intrinsic.sensorWidth
                                camerainstrinsic_dict['pixelSize'] = current_cameraProjections.intrinsic.pixelSize
                                camerainstrinsic_dict['sourceToDetectorDistance'] = current_cameraProjections.intrinsic.sourceToDetectorDistance
                                cameraProjections_dict['intrinsic'] = camerainstrinsic_dict
                                cameraProjections_dict['extrinsic'] = list(request.cameraProjections[i].extrinsic.data)   
                                cameraProjections_dict_.append(cameraProjections_dict)
                            msgdict['cameraProjections'] = cameraProjections_dict_ 
                            transforms = []
                            for i in range(len(request.volumesWorldFromAnatomical)):
                                transforms.append([x for x in request.volumesWorldFromAnatomical[i].data])
                            msgdict['volumesWorldFromAnatomical'] = transforms 
                        with messages.ProjectResponse.from_bytes(project_response) as response:
                            images_dict_ = []
                            for i in range(len(response.images)):
                                current_image = response.images[i]
                                bytes = current_image.data
                                base64_bytes = base64.b64encode(bytes)
                                base64_string = base64_bytes.decode("ascii") 
                                images_dict_.append(base64_string)
                                
                                image = Image.open(BytesIO(bytes))
                                image_filename = str(response.requestId) + ".jpg"
                                image_path = os.path.join(self.log_root_path, image_filename)
                                image.save(image_path)
                            msgdict['image'] = images_dict_
                            
                        # print(msgdict)
                        
                        # save msgdict to json
                        json_filename = str(requestId) + ".json"
                        json_path = os.path.join(self.log_root_path, json_filename)
                        with open(json_path, 'w') as json_file:
                            json.dump(msgdict, json_file)
                            print(f"json file saved to {json_path}")
                            
                        requestId = None
                        single_shot_request = None
                        project_request = None
                        project_response = None
                        
                await asyncio.sleep(0.001)

            except DeepDRRServerException as e:
                print(f"server exception: {e}")
                await pub_socket.send_multipart([b"/server_exception/", e.status_response().to_bytes()])


    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass


@app.command()
@unwrap_typer_param
def main(
        rep_port=typer.Argument(40120),
        pub_port=typer.Argument(40121),
        sub_port=typer.Argument(40122),
        # log_root_path=typer.Argument("pvrlogs")
):

    print(f"rep_port: {rep_port}")
    print(f"pub_port: {pub_port}")
    print(f"sub_port: {sub_port}")

    single_shot_log_dir_default = Path(r"logs/sslogs") 
    single_shot_log_dir = Path(os.environ.get("SINGLE_SHOT_LOG_DIR", single_shot_log_dir_default)).resolve()
    print(f"single_shot_log_dir: {single_shot_log_dir}")

    with zmq_no_linger_context(zmq.asyncio.Context()) as context:
        with SingleShotServer(context, rep_port, pub_port, sub_port, single_shot_log_dir) as time_server:
            asyncio.run(time_server.start())


if __name__ == '__main__':
    app()

