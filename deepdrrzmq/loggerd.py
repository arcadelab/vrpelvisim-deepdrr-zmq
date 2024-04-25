import asyncio
import logging
import os
import random
import string
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


class LogWriter:
    """
    Stream wrapper for writing to a log file.5
    """
    def __init__(self, fileobj):
        self.filestream = fileobj

    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        pass

    def write(self, data):
        return self.filestream.write(data)


class LogShardWriter:
    """
    Stream wrapper for writing to a log file. Automatically switches to a new
    file when the current one reaches a certain size.
    """
    def __init__(self, pattern, maxcount, maxsize, start_shard=0, verbose=False, **kw):
        """
        :param pattern: The pattern for the log file names. Must contain a single %d placeholder.
        :param maxcount: The maximum number of messages per file.
        :param maxsize: The maximum size of a file in bytes.
        :param start_shard: The shard number to start with.
        :param verbose: Whether to print information about the log files.
        :param kw: Additional keyword arguments for the LogWriter.
        """
        self.verbose = 1
        self.maxcount = maxcount
        self.maxsize = maxsize
        self.kw = kw

        self.logstream = None
        self.shard = start_shard
        self.pattern = pattern
        self.total = 0
        self.count = 0
        self.size = 0
        self.fname = None
        self.next_stream()


    def next_stream(self):
        """
        Switch to the next log file.
        """
        self.finish()
        self.fname = self.pattern % self.shard
        if self.verbose:
            print(
                "# writing",
                self.fname,
                self.count,
                "%.1f GB" % (self.size / 1e9),
                self.total,
            )
        self.shard += 1
        stream = open(self.fname, "wb")
        self.logstream = LogWriter(stream, **self.kw)
        self.count = 0
        self.size = 0

    def write(self, data):
        """
        Write data to the current log file. If the file is full, switch to a new one.
        :param data: The data to write.
        """
        if (
            self.logstream is None
            or self.count >= self.maxcount
            or self.size >= self.maxsize
        ):
            self.next_stream()
        size = self.logstream.write(data)
        self.count += 1
        self.total += 1
        self.size += size

    def finish(self):
        """
        Close the current log file.
        """
        if self.logstream is not None:
            self.logstream.close()
            assert self.fname is not None
            self.logstream = None

    def close(self):
        """
        Close the current log file stream.
        """
        self.finish()

    def __enter__(self):
        return self

    def __exit__(self, *args, **kw):
        self.close()


class LogRecorder:
    """
    Context manager for logging data from the surgical simulation.
    """
    def __init__(self, log_root_path, **kw):
        """
        :param log_root_path: The path to the root folder where the logs should be stored.
        :param kw: Additional keyword arguments for the LogShardWriter.
        """
        self.kw = kw
        self.log_root_path = log_root_path
        self.session = None
        self.session_id = None

    def new_session(self):
        """
        Start a new logging session.
        """
        self.finish()
        self.session_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=16))

        date_string = time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime())
        log_foldername = f"{self.session_id}--{date_string}"
        log_filename = f"{self.session_id}--{date_string}--%d.vrpslog"

        log_folder = Path(self.log_root_path) / log_foldername
        log_folder.mkdir(parents=True, exist_ok=True)

        log_path = log_folder / log_filename

        self.session = LogShardWriter(str(log_path), **self.kw)

    def stop_session(self):
        """
        Stop the current logging session.
        """
        self.finish()

    def write(self, data):
        """
        Write data to the current log session if there is one.
        """
        if (
            self.session is None
        ):
            return
        self.session.write(data)

    def finish(self):
        """
        Close the current log session.
        """
        if self.session is not None:
            self.session.close()
            self.session = None
            self.session_id = None

    def close(self):
        """
        Close the log session.
        """
        self.finish()

    def __enter__(self):
        return self

    def __exit__(self, *args, **kw):
        self.close()


class LoggerServer:
    """
    Server for logging data from the surgical simulation.
    """
    def __init__(self, context, addr, rep_port, pub_port, sub_port, hwm, log_dir):
        """
        Create a new LoggerServer instance.
        
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
        self.log_dir = log_dir
        
        self.log_recorder = LogRecorder(log_dir, maxcount = 1e15, maxsize = 100e6)

    async def start(self):
        recording_logger_processor = asyncio.create_task(self.recording_logger_server())
        status_processor = asyncio.create_task(self.status_server())
        await asyncio.gather(recording_logger_processor, status_processor)

    async def recording_logger_server(self):
        """
        Server for logging recording data from the surgical simulation.
        """
        sub_topic_list = [b""]
        sub_socket = self.zmq_setup_socket(zmq.SUB, self.sub_port, topic_list=sub_topic_list)
        pub_socket = self.zmq_setup_socket(zmq.PUB, self.pub_port)

        with self.log_recorder as log_file:
            while True:
                try:
                    latest_msgs = await zmq_poll_latest(sub_socket)

                    for topic, data in latest_msgs.items():
                        # write to log file
                        msg = messages.LogEntry.new_message()
                        msg.logMonoTime = time.time()
                        msg.topic = topic
                        msg.data = data
                        log_file.write(msg.to_bytes())

                        # process loggerd commands
                        if topic == b"/loggerd/stop/":
                            log_file.stop_session()
                        elif topic == b"/loggerd/start/":
                            log_file.new_session()

                    await asyncio.sleep(0.001)

                except DeepDRRServerException as e:
                    print(f"server exception: {e}")
                    await pub_socket.send_multipart([b"/server_exception/", e.status_response().to_bytes()])

    async def status_server(self):
        """
        Server for sending the status of the logger.
        """
        pub_socket = self.zmq_setup_socket(zmq.PUB, self.pub_port)

        while True:
            await asyncio.sleep(1)
            msg = messages.LoggerStatus.new_message()
            msg.recording = self.log_recorder.session_id is not None
            msg.sessionId = self.log_recorder.session_id or ""
            await pub_socket.send_multipart([b"/loggerd/status/", msg.to_bytes()])
            
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
    config_dirs = config['dirs']

    addr = config_network['addr_localhost']
    rep_port = config_network['rep_port']
    pub_port = config_network['pub_port']
    sub_port = config_network['sub_port']
    hwm = config_network['hwm']
    
    # REPLAY_LOG_DIR environment variable is set by the docker container
    default_vrps_log_dir = config_dirs['default_vrps_log_dir']
    vrps_log_dir = Path(os.environ.get("REPLAY_LOG_DIR", default_vrps_log_dir)).resolve()

    print(f"""
    [{Path(__file__).stem}]
        addr: {addr}
        rep_port: {rep_port}
        pub_port: {pub_port}
        sub_port: {sub_port}
        hwm: {hwm}
        default_vrps_log_dir: {default_vrps_log_dir}
        vrps_log_dir: {vrps_log_dir}
    """)
    logging.info(f"[{Path(__file__).stem}] vrps_log_dir: {vrps_log_dir}")
    
    with zmq_no_linger_context(zmq.asyncio.Context()) as context:
        with LoggerServer(context, addr, rep_port, pub_port, sub_port, hwm, vrps_log_dir) as logger_server:
            asyncio.run(logger_server.start())
            

if __name__ == '__main__':
    app()
