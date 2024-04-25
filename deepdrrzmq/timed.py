import asyncio
import logging
import os
import time
from pathlib import Path

import capnp
import typer
import zmq.asyncio

from deepdrrzmq.utils.config_util import config_path, load_config
from deepdrrzmq.utils.server_util import messages, make_response, DeepDRRServerException
from deepdrrzmq.utils.typer_util import unwrap_typer_param
from deepdrrzmq.utils.zmq_util import zmq_no_linger_context, zmq_poll_latest


app = typer.Typer(pretty_exceptions_show_locals=False)


class TimeServer:
    """A class that implements a time server.

    The time server is a process that publishes the current time to all
    subscribers. The time is published once per second. The time is used
    to synchronize the multiplayer messages.
    """
    def __init__(self, context, addr, rep_port, pub_port, sub_port, hwm):
        """
        :param context: The zmq context.
        :param addr: The address of the ZMQ server.
        :param rep_port: The port number for REP (request-reply) socket connections.
        :param pub_port: The port number for PUB (publish) socket connections.
        :param sub_port: The port number for SUB (subscribe) socket connections.
        :param hwm: The high water mark (HWM) for message buffering.
        """
        self.context = context
        self.addr = addr
        self.rep_port = rep_port
        self.pub_port = pub_port
        self.sub_port = sub_port
        self.hwm = hwm

        self.disable_until = 0

    async def start(self):
        time_server_processor = asyncio.create_task(self.time_server())
        command_loop_processor = asyncio.create_task(self.command_loop())
        await asyncio.gather(time_server_processor, command_loop_processor)

    async def command_loop(self):
        sub_topic_list = [b"/timed/in/"]
        sub_socket = self.zmq_setup_socket(zmq.SUB, self.sub_port, topic_list=sub_topic_list)
        pub_socket = self.zmq_setup_socket(zmq.PUB, self.pub_port)

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
        pub_socket = self.zmq_setup_socket(zmq.PUB, self.pub_port)

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
    
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass


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
    
    with zmq_no_linger_context(zmq.asyncio.Context()) as context:
        with TimeServer(context, addr, rep_port, pub_port, sub_port, hwm) as time_server:
            asyncio.run(time_server.start())
            

if __name__ == '__main__':
    app()
