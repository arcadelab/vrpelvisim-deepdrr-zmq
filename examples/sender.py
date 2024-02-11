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
    bind=typer.Option(True, help="bind to the port instead of connecting to it"),
    ):
    file_path = os.path.dirname(os.path.realpath(__file__))
    messages = capnp.load(os.path.join(file_path, 'messages.capnp'))

    with zmq_no_linger_context() as context:
        pub_socket = context.socket(zmq.PUB)
        pub_socket.hwm = 2
        
        if bind:
            connection_str = f"tcp://*:{port}"
            pub_socket.bind(connection_str)
        else:
            connection_str = f"tcp://{ip}:{port}"
            pub_socket.connect(connection_str)

        print(f"connected to {connection_str}")

        start_time = time.time()
        weights = [[random.uniform(-1, 1) for _ in range(3)] for _ in range(5)]
        scale = 2

        while True:
            hand_pose = messages.HandPose.new_message()

            fingers = hand_pose.init('fingers', 5)

            for i in range(5):
                fingers[i].x = math.sin(time.time() * weights[i][0] * scale)
                fingers[i].y = math.sin(time.time() * weights[i][1] * scale)
                fingers[i].z = math.sin(time.time() * weights[i][2] * scale)

            pub_socket.send_multipart([b"hand_pose/", hand_pose.to_bytes()])
            # print(f"sending: {hand_pose}")
            time.sleep(1/10) # simulate bad network conditions (10 fps)



if __name__ == '__main__':
    try:
        app()
    except KeyboardInterrupt:
        pass
    print("exiting..")