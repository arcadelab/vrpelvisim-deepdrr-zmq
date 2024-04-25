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


class PrintServer:
    """
    A simple server that prints all messages it receives for debugging purposes.
    """
    def __init__(self, context, addr, rep_port, pub_port, sub_port, hwm):
        """
        Create a new PrintServer instance.
        
        :param context: The zmq context.
        :param addr: The address of the ZMQ server.
        :param rep_port: The port number for REP (request-reply) socket connections.
        :param pub_port: The port number for PUB (publish) socket connections.
        :param sub_port: The port number for SUB (subscribe) socket connections.
        :param hwm: The high water mark (HWM) for message buffering.
        :param log_dir: The directory for saving the logger logs.
        """
        self.context = context
        self.addr = addr
        self.rep_port = rep_port
        self.pub_port = pub_port
        self.sub_port = sub_port
        self.hwm = hwm

    async def start(self):
        time_server_processor = asyncio.create_task(self.print_server())
        await asyncio.gather(time_server_processor)

    async def print_server(self):
        sub_topic_list = [b""]
        sub_socket = self.zmq_setup_socket(zmq.SUB, self.sub_port, topic_list=sub_topic_list)
        pub_socket = self.zmq_setup_socket(zmq.PUB, self.pub_port)

        while True:

            try:
                latest_msgs = await zmq_poll_latest(sub_socket)

                for topic, data in latest_msgs.items():
                    print(topic, data)

                if len(latest_msgs) == 0:
                    print("no messages")

                time.sleep(1)

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
        with PrintServer(context, addr, rep_port, pub_port, sub_port, hwm) as print_server:
            asyncio.run(print_server.start())


if __name__ == '__main__':
    app()
