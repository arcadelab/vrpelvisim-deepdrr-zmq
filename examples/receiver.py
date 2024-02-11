import json
import math
import os
import random
import sys
import time
from io import BytesIO
import typer

import capnp
import zmq

from zmqutil import zmq_no_linger_context

app = typer.Typer()

@app.command()
def main(
    ip=typer.Argument('localhost', help="ip address of the receiver"),
    port=typer.Argument(40000, help="port of the receiver"),
    bind: bool=typer.Option(False, help="bind to the port instead of connecting to it"),
    ):
    file_path = os.path.dirname(os.path.realpath(__file__))
    messages = capnp.load(os.path.join(file_path, 'messages.capnp'))

    with zmq_no_linger_context() as context:
        pub_socket = context.socket(zmq.SUB)
        pub_socket.hwm = 2
        
        if bind:
            connection_str = f"tcp://*:{port}"
            pub_socket.bind(connection_str)
        else:
            connection_str = f"tcp://{ip}:{port}"
            pub_socket.connect(connection_str)

        pub_socket.setsockopt_string(zmq.SUBSCRIBE, "hand_pose/")
        print(f"connected to {connection_str}")

        while True:
            topic, data = pub_socket.recv_multipart()
            with messages.HandPose.from_bytes(data) as hand_pose:
                print(f"got: {hand_pose}")



if __name__ == '__main__':
    try:
        app()
    except KeyboardInterrupt:
        pass
    print("exiting..")