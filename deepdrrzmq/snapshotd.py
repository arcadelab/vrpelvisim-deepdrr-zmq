import asyncio
import capnp
import os
import typer
import zmq.asyncio
from pathlib import Path
from deepdrrzmq.utils.zmq_util import zmq_no_linger_context, zmq_poll_latest
from deepdrrzmq.utils.config_util import config_path, load_config
from .utils.typer_util import unwrap_typer_param
from .utils.server_util import make_response, DeepDRRServerException, messages

import json
import base64 
from io import BytesIO
from PIL import Image
from datetime import datetime


app = typer.Typer(pretty_exceptions_show_locals=False)


class SnapshotServer:
    """
    Server for logging snapshot data from the surgical simulation.
    """
    def __init__(self, context, addr, rep_port, pub_port, sub_port, hwm, log_root_path):
        """
        Create a new SnapshotServer instance.
        
        :param context: The zmq context.
        :param addr: The address of the ZMQ server.
        :param rep_port: The port number for REP (request-reply) socket connections.
        :param pub_port: The port number for PUB (publish) socket connections.
        :param sub_port: The port number for SUB (subscribe) socket connections.
        :param hwm: The high water mark (HWM) for message buffering.
        :param log_root_path: The root path for saving the snapshot logs.
        """
        self.context = context
        self.addr = addr
        self.rep_port = rep_port
        self.pub_port = pub_port
        self.sub_port = sub_port
        self.hwm = hwm
        self.log_root_path = log_root_path
        self.log_root_path.mkdir(parents=True, exist_ok=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    async def start(self):
        snapshot_logger_processor = asyncio.create_task(self.snapshot_logger_server())
        await asyncio.gather(snapshot_logger_processor)

    async def snapshot_logger_server(self):
        """
        Server for logging snapshot data from the surgical simulation.
        """
        sub_topic_list = [b"/snapshot_request/", b"/priority_project_request/", b"/priority_project_response/"]
        sub_socket = self.zmq_setup_socket(zmq.SUB, self.sub_port, topic_list=sub_topic_list)
        pub_socket = self.zmq_setup_socket(zmq.PUB, self.sub_port)
        
        requestId = None
        snapshot_request = priority_project_request = priority_project_response = None
        
        while True:
            try:
                latest_msgs = await zmq_poll_latest(sub_socket, max_skip=0)

                for topic, data in latest_msgs.items():
                    
                    # this might not come first
                    if topic.startswith(b"/snapshot_request/"):
                        with messages.SnapshotRequest.from_bytes(data) as request:
                            if request.requestId:
                                requestId = request.requestId
                                snapshot_request = data
                                priority_project_request = None
                                priority_project_response = None
                            print(f"snapshot_request: {requestId}")

                    if topic.startswith(b"/priority_project_request/"):
                        with messages.ProjectRequest.from_bytes(data) as request:
                            if request.requestId and request.requestId == requestId:
                                priority_project_request = data
                    
                    if topic.startswith(b"/priority_project_response/"):
                        with messages.ProjectResponse.from_bytes(data) as response:
                            if response.requestId and response.requestId == requestId:
                                priority_project_response = data

                    if snapshot_request and priority_project_request and priority_project_response:
                        msgdict = {}
                        with messages.SnapshotRequest.from_bytes(snapshot_request) as request:
                            msgdict.update(self.capnp_message_to_dict(request))
                        with messages.ProjectRequest.from_bytes(priority_project_request) as request:
                            msgdict.update(self.capnp_message_to_dict(request))
                        with messages.ProjectResponse.from_bytes(priority_project_response) as response:
                            msgdict.update(self.capnp_message_to_dict(response))
                        
                        # extract fields from msgdict and create filename
                        userId = msgdict.get("userId")
                        patientCaseId = msgdict.get("patientCaseId")
                        standardViewName = msgdict.get("standardViewName")
                        standardViewCount = msgdict.get("standardViewCount")
                        image_list = msgdict.get('images')
                        
                        # create filename and file directory
                        file_datetime = datetime.now().strftime("%Y%m%d-%H%M%S")
                        filename = f"{file_datetime}_{userId}_{patientCaseId}_{standardViewName}_{standardViewCount}"
                        file_dir = self.log_root_path / userId / patientCaseId / standardViewName
                        file_dir.mkdir(parents=True, exist_ok=True)
                        
                        # save msgdict to json
                        json_path = file_dir / f"{filename}.json"
                        self.save_json(msgdict, json_path)
                        
                        # save msgdict images
                        self.save_image(image_list, file_dir, filename)
                            
                        requestId = None
                        snapshot_request = priority_project_request = priority_project_response = None
                        
                await asyncio.sleep(0)

            except DeepDRRServerException as e:
                print(f"server exception: {e}")
                await pub_socket.send_multipart([b"/server_exception/", e.status_response().to_bytes()])

    def zmq_setup_socket(self, socket_type, port, topic_list=None):
        """ 
        ZMQ socket setup.
        """
        socket = self.context.socket(socket_type)
        socket.hwm = self.hwm
        socket.connect(f"tcp://{self.addr}:{port}")
        
        if topic_list:
            for topic in topic_list:
                socket.subscribe(topic)
        return socket

    def capnp_message_to_dict(self, message):
        """
        Converts a Cap'n Proto message to a dictionary, handling nested messages and lists.
        """
        def convert_field_value_type(field_value):
            # field_value is a capnp.lib.capnp._DynamicStructReader
            if isinstance(field_value, capnp.lib.capnp._DynamicStructReader):
                return self.capnp_message_to_dict(field_value)
            # field_value is a capnp.lib.capnp._DynamicListReader
            elif isinstance(field_value, capnp.lib.capnp._DynamicListReader):
                return [convert_field_value_type(value) for value in field_value]
            # field_value is a bytes: convert to base64 string to make it JSON-serializable
            elif isinstance(field_value, bytes):
                base64_bytes = base64.b64encode(field_value)
                base64_string = base64_bytes.decode("ascii")
                return base64_string  
            return field_value
        
        capnp_dict = {}
        for field in message.schema.fields:
            field_value = getattr(message, field)
            converted_field_value = convert_field_value_type(field_value)
            capnp_dict[field] = converted_field_value
        
        return capnp_dict

    def save_json(self, data, json_path):
        """
        Saves JSON data to a file, with error handling.
        """
        try:
            with open(json_path, 'w', encoding='utf-8') as file:
                json.dump(data, file, indent=4)
        except IOError as e:
            print(f"Error writing to file {json_path}: {e}")
            
    def save_image(self, image_list, file_dir, filename):
        """
        Save iamges from base64 strings to files.
        """
        for image_dict in image_list:
            image_base64_string = image_dict.get("data")
            image_base64_bytes = image_base64_string.encode("ascii")
            image_bytes = base64.b64decode(image_base64_bytes) 
            image = Image.open(BytesIO(image_bytes))
            image_path = file_dir / f"{filename}.jpg"
            image.save(image_path)


@app.command()
@unwrap_typer_param
def main(config_path: Path = typer.Option(config_path, help="Path to the configuration file")):
    # Load the configuration
    config = load_config(config_path)
    config_network = config['network']

    addr = config_network['addr_localhost']
    rep_port = config_network['rep_port']
    pub_port = config_network['pub_port']
    sub_port = config_network['sub_port']
    hwm = config_network['hwm']

    print(f"""
    [{Path(__file__).stem}]
        addr: {addr}
        rep_port: {rep_port}
        pub_port: {pub_port}
        sub_port: {sub_port}
        hwm: {hwm}
    """)
    
    snapshot_logs_dir_default = Path(r"logs/sslogs") 
    snapshot_logs_dir = Path(os.environ.get("SNAPSHOT_LOG_DIR", snapshot_logs_dir_default)).resolve()
    print(f"snapshot_logs_dir: {snapshot_logs_dir}")
    
    with zmq_no_linger_context(zmq.asyncio.Context()) as context:
        with SnapshotServer(context, addr, rep_port, pub_port, sub_port, hwm, snapshot_logs_dir) as time_server:
            asyncio.run(time_server.start())


if __name__ == '__main__':
    app()
