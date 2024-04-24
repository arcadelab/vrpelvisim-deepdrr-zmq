"""
This module implements a zmq pub/sub proxy server.

The proxy server is used to forward messages from the client to the
server and vice versa. It uses the ZeroMQ XPUB/XSUB pattern to
handle requests from the client.
"""

from pathlib import Path
import signal

import typer
import zmq

from deepdrrzmq.utils.config_util import config_path, load_config
from deepdrrzmq.utils.typer_util import unwrap_typer_param


app = typer.Typer(pretty_exceptions_show_locals=False)


@app.command()
@unwrap_typer_param
def main(config_path: Path = typer.Option(config_path, help="Path to the configuration file")):
    # Load the configuration
    config = load_config(config_path)
    config_network = config['network']

    XSUB_PORT = config_network['XSUB']
    XPUB_PORT = config_network['XPUB']
    
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    context = zmq.Context()

    backend = context.socket(zmq.XSUB)
    back_addr = f"tcp://*:{XSUB_PORT}"
    backend.bind(back_addr)

    frontend = context.socket(zmq.XPUB)
    front_addr = f"tcp://*:{XPUB_PORT}"
    frontend.bind(front_addr)

    print(f"""
    [{Path(__file__).stem}]
        Proxy Running...
        XSUB_PORT: {XSUB_PORT}
        back_addr: {back_addr}
        XPUB_PORT: {XPUB_PORT}
        front_addr: {front_addr}
    """)
    
    zmq.proxy(frontend, backend)
    
    print(f"""
    [{Path(__file__).stem}]
        Exiting...
    """)
    
    frontend.close()
    backend.close()
    context.term()


if __name__ == "__main__":
    app()
