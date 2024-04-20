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
import aiofiles
import json


# app = typer.Typer()
app = typer.Typer(pretty_exceptions_show_locals=False)


class SnapshotServer:
    """
    Server for logging snapshot data from the surgical simulation.
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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    async def start(self):
        recorder_loop = self.logger_server()
        await asyncio.gather(recorder_loop)

    async def logger_server(self):
        """
        Server for logging snapshot data from the surgical simulation.
        """
        sub_socket = self.context.socket(zmq.SUB)
        sub_socket.hwm = 10000

        pub_socket = self.context.socket(zmq.PUB)
        pub_socket.hwm = 10000

        pub_socket.connect(f"tcp://localhost:{self.pub_port}")
        sub_socket.connect(f"tcp://localhost:{self.sub_port}")

        sub_socket.subscribe(b"/snapshot_request/")
        sub_socket.subscribe(b"project_request/")
        sub_socket.subscribe(b"/project_response/")
        
        requestId = None
        snapshot_request = None
        project_request = None
        project_response = None
        while True:
            try:
                latest_msgs = await zmq_poll_latest(sub_socket)

                for topic, data in latest_msgs.items():
                    
                    # this might not come first
                    if topic.startswith(b"/snapshot_request/"):
                        with messages.SnapshotRequest.from_bytes(data) as request:
                            requestId = request.requestId
                            snapshot_request = data
                            project_request = None
                            project_response = None
                        print(f"snapshot request: {topic}")

                    if topic.startswith(b"project_request/"):
                        with messages.ProjectRequest.from_bytes(data) as request:
                            if request.requestId == requestId:
                                project_request = data
                    
                    if topic.startswith(b"/project_response/"):
                        with messages.ProjectResponse.from_bytes(data) as response:
                            if response.requestId == requestId:
                                project_response = data

                    if snapshot_request and project_request and project_response:
                        msgdict = {}
                        with messages.SnapshotRequest.from_bytes(snapshot_request) as request:
                            msgdict.update(self.capnp_message_to_dict(request))
                        with messages.ProjectRequest.from_bytes(project_request) as request:
                            msgdict.update(self.capnp_message_to_dict(request))
                        with messages.ProjectResponse.from_bytes(project_response) as response:
                            # msgdict.update(self.capnp_message_to_dict(response))
                            images_dict_ = []
                            for image in response.images:
                                bytes = image.data
                                print(type(bytes), bytes)
                                base64_bytes = base64.b64encode(bytes)
                                base64_string = base64_bytes.decode("ascii") 
                                images_dict_.append(base64_string)
                                
                                image = Image.open(BytesIO(bytes))
                                image_filename = f"{requestId}.jpg"
                                image_path = self.log_root_path / image_filename
                                image.save(image_path)
                            msgdict['image'] = images_dict_
                            
                        # print(msgdict)
                        
                        # save msgdict to json
                        json_filename = f"{requestId}.json"
                        json_path = self.log_root_path / json_filename
                        with open(json_path, 'w') as json_file:
                            json.dump(msgdict, json_file)
                            print(f"json file saved to {json_path}")
                            
                        requestId = None
                        snapshot_request = None
                        project_request = None
                        project_response = None
                        
                await asyncio.sleep(0.001)

            except DeepDRRServerException as e:
                print(f"server exception: {e}")
                await pub_socket.send_multipart([b"/server_exception/", e.status_response().to_bytes()])

    def capnp_message_to_dict(self, message):
        """
        Converts a Cap'n Proto message to a dictionary, handling nested messages and lists.
        """
        capnp_dict = {}
        for field in message.schema.fields:
            field_value = getattr(message, field)

            if isinstance(field_value, bytes):
                print(f"field {field} = [{type(field_value)}]: {field_value}")

            # Recursively handle nested Cap'n Proto messages and lists
            if isinstance(field_value, capnp.lib.capnp._DynamicStructReader):
                capnp_dict[field] = self.capnp_message_to_dict(field_value)
            elif isinstance(field_value, capnp.lib.capnp._DynamicListReader):
                capnp_dict[field] = [
                    self.capnp_message_to_dict(value) if isinstance(value, capnp.lib.capnp._DynamicStructReader) else value 
                    for value in field_value
                ]
            else:
                capnp_dict[field] = field_value
        return capnp_dict
    
    async def save_image(data, img_path):
        """
        Asynchronously saves an image to the disk.
        """
        async with aiofiles.open(img_path, 'wb') as file:
            await file.write(data)

    async def save_json(data, json_path):
        """
        Asynchronously saves data to a JSON file.
        """
        async with aiofiles.open(json_path, 'w') as file:
            await file.write(json.dumps(data, indent=4))


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

    snapshot_logs_dir_default = Path(r"logs/sslogs") 
    snapshot_logs_dir = Path(os.environ.get("SNAPSHOT_LOG_DIR", snapshot_logs_dir_default)).resolve()
    print(f"snapshot_logs_dir: {snapshot_logs_dir}")

    with zmq_no_linger_context(zmq.asyncio.Context()) as context:
        with SnapshotServer(context, rep_port, pub_port, sub_port, snapshot_logs_dir) as time_server:
            asyncio.run(time_server.start())


if __name__ == '__main__':
    app()
