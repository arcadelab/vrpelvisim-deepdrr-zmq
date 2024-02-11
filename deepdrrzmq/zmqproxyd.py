"""
This module implements a zmq pub/sub proxy server.

The proxy server is used to forward messages from the client to the
server and vice versa. It uses the ZeroMQ XPUB/XSUB pattern to
handle requests from the client.
"""

import signal
import zmq

XSUB_PORT = 40101
XPUB_PORT = 40102

def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    context = zmq.Context()

    frontend = context.socket(zmq.XPUB)
    front_addr = f"tcp://*:{XPUB_PORT}"
    frontend.bind(front_addr)

    backend = context.socket(zmq.XSUB)
    back_addr = f"tcp://*:{XSUB_PORT}"
    backend.bind(back_addr)

    print('proxy running')
    print('xpub: ', front_addr)
    print('xsub: ', back_addr)
    zmq.proxy(frontend, backend)
    print('exiting..')

    frontend.close()
    backend.close()
    context.term()

if __name__ == "__main__":
    main()