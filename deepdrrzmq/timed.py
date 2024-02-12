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


# app = typer.Typer()
app = typer.Typer(pretty_exceptions_show_locals=False)



class TimeServer:
    """A class that implements a time server.

    The time server is a process that publishes the current time to all
    subscribers. The time is published once per second. The time is used
    to synchronize the multiplayer messages.
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

        self.disable_until = 0

    async def start(self):
        await asyncio.gather(
            self.time_server(),
            self.command_loop(),
        )

    async def command_loop(self):
        sub_socket = self.context.socket(zmq.SUB)
        sub_socket.hwm = 10000

        pub_socket = self.context.socket(zmq.PUB)
        pub_socket.hwm = 10000

        pub_socket.connect(f"tcp://localhost:{self.pub_port}")
        sub_socket.connect(f"tcp://localhost:{self.sub_port}")

        sub_socket.subscribe(b"/timed/in/")

        while True:
            try:
                latest_msgs = await zmq_poll_latest(sub_socket)

                for topic, data in latest_msgs.items():
                    if topic == b"/timed/in/block/":
                        self.disable_until = time.time() + 10
                await asyncio.sleep(0.1)

            except DeepDRRServerException as e:
                print(f"server exception: {e}")
                await pub_socket.send_multipart([b"/server_exception/", e.status_response().to_bytes()])
            

    async def time_server(self):
        sub_socket = self.context.socket(zmq.SUB)
        sub_socket.hwm = 10000

        pub_socket = self.context.socket(zmq.PUB)
        pub_socket.hwm = 10000

        pub_socket.connect(f"tcp://localhost:{self.pub_port}")
        sub_socket.connect(f"tcp://localhost:{self.sub_port}")

        while True:
            if time.time() > self.disable_until:
                # make a new time object with the current time
                time_msg = messages.Time.new_message()
                time_msg.millis = time.time()

                # send the time object on the /mp/time topic
                await pub_socket.send_multipart([b"/mp/time/", time_msg.to_bytes()])
            else:
                print("timed is disabled")

            await asyncio.sleep(1)


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
):

    print(f"rep_port: {rep_port}")
    print(f"pub_port: {pub_port}")
    print(f"sub_port: {sub_port}")

    with zmq_no_linger_context(zmq.asyncio.Context()) as context:
        with TimeServer(context, rep_port, pub_port, sub_port) as time_server:
            asyncio.run(time_server.start())


if __name__ == '__main__':
    app()

