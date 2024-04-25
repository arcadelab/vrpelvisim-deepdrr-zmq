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


class LogReplayer:
    def __init__(self, logfolderpath):
        self.logfolderpath = logfolderpath
        self.next_file_idx = 0
        self._current_time = None
        self.current_entryiter = None
        # self._loop = False
        self.next_buffered = None
        self._starttime = None
        self._endtime = None
        self._allfiles = None

    @property
    def allfiles(self):
        if self._allfiles is None:
            listfiles = list(Path(self.logfolderpath).glob("*.vrpslog"))
            self._allfiles = sorted(listfiles, key=lambda x: int(x.stem.split("--")[-1]))
            print(f"allfiles: {self._allfiles} {self.logfolderpath}")
        return self._allfiles

    # @property
    # def loop(self):
    #     return self._loop
    
    # @loop.setter
    # def loop(self, state):
    #     self._loop = state

    @property
    def starttime(self):
        if self._starttime is None:
            firstfile = self.allfiles[0]
            firstentry = next(messages.LogEntry.read_multiple_bytes(firstfile.read_bytes()))
            self._starttime = firstentry.logMonoTime
        return self._starttime

    @property
    def endtime(self):
        if self._endtime is None:
            self._endtime = 0
            lastfile = self.allfiles[-1]
            for logentry in messages.LogEntry.read_multiple_bytes(lastfile.read_bytes()):
                self._endtime = logentry.logMonoTime
        return self._endtime
    
    @property
    def current_time(self):
        if self._current_time is None:
            self.current_time = self.starttime
        return self._current_time
    
    @current_time.setter
    def current_time(self, time):
        self._current_time = time

    def __iter__(self):
        return self

    def __next__(self):
        # if self.next_buffered is not None:
        #     msg = self.next_buffered
        #     self.next_buffered = None
        #     self.current_time = msg.logMonoTime
        #     return msg
        if self.current_entryiter is None:
            if self.next_file_idx >= len(self.allfiles):
                # if self.loop:
                #     self.next_file_idx = 0
                # else:
                #     self.current_time = None
                self.next_file_idx += 1
                raise StopIteration
            self.current_entryiter = messages.LogEntry.read_multiple_bytes(self.allfiles[self.next_file_idx].read_bytes())
            self.next_file_idx += 1
        try:
            msg = next(self.current_entryiter)
            self.current_time = msg.logMonoTime
            return msg
        except StopIteration:
            self.current_entryiter = None
            msg = next(self)
            self.current_time = msg.logMonoTime
            return msg
        
    def seek_time(self, time):
        print(f"seek_time: {time} current_time: {self.current_time} percent: {(time - self.starttime) / (self.endtime - self.starttime) * 100}")
        if time < self.current_time:
            self.next_file_idx = 0
            self.current_entryiter = None
        self.next_buffered = None
        
        try:
            while self.current_time < time:
                next(self) # TODO: this seeks one past
        except StopIteration:
            pass
        self.current_time = time


class LogReplayServer:
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
        
        self.log_replayer = None
        self._play_state = False
        self.log_id = None
        self.log_time_offset = None
        self.loop = False
        self.playback_time = None

        self._pathes_sorted_mtime = None
        self.enabled = False

    @property
    def pathes_sorted_mtime(self):
        if self._pathes_sorted_mtime is None:
            pathes = list(Path(self.log_dir).glob("*"))
            self._pathes_sorted_mtime = [p for p in sorted(pathes, key=os.path.getmtime) if p.is_dir()]
        return self._pathes_sorted_mtime
    
    def invalidate_pathes_sorted_mtime(self):
        self._pathes_sorted_mtime = None

    @property
    def play_state(self):
        return self._play_state
    
    @play_state.setter
    def play_state(self, state):
        if state and self.log_replayer is None:
            raise DeepDRRServerException(400, "no log loaded")
        
        self._play_state = state
        if state:
            self.log_time_offset = time.time() - self.log_replayer.current_time
            self.logentry_valid = False
            print(f"play_state: {self._play_state=} {self.log_time_offset=} {self.log_replayer.current_time=}")
        else:
            self.log_time_offset = None

    async def start(self):
        command_loop_processor = asyncio.create_task(self.command_loop())
        status_loop_processor = asyncio.create_task(self.status_loop())
        loglist_loop_processor = asyncio.create_task(self.loglist_loop())
        replay_loop_processor = asyncio.create_task(self.replay_loop())
        blocker_loop_processor = asyncio.create_task(self.blocker_loop())
        await asyncio.gather(
            command_loop_processor, 
            status_loop_processor, 
            loglist_loop_processor, 
            replay_loop_processor, 
            blocker_loop_processor
        )

    async def command_loop(self):
        sub_topic_list = [b"/replayd/in/"]
        sub_socket = self.zmq_setup_socket(zmq.SUB, self.sub_port, topic_list=sub_topic_list)
        pub_socket = self.zmq_setup_socket(zmq.PUB, self.pub_port)

        while True:
            try:
                latest_msgs = await zmq_poll_latest(sub_socket)

                if b"/replayd/in/enable/" in latest_msgs:
                    self.enabled = True
                    print("enable")

                if not self.enabled:
                    await asyncio.sleep(0.1)
                    continue
                
                if b"/replayd/in/disable/" in latest_msgs:
                    self.enabled = False
                    self.play_state = False
                    print("disable")

                if b"/replayd/in/load/" in latest_msgs:
                    data = latest_msgs[b"/replayd/in/load/"]
                    self.play_state = False
                    with messages.LoadLogRequest.from_bytes(data) as msg:
                        if msg.logId not in [p.name for p in self.pathes_sorted_mtime]:
                            raise DeepDRRServerException(400, f"log {msg.logId} not found")
                        self.log_id = msg.logId
                        self.log_replayer = LogReplayer(Path(self.log_dir) / msg.logId)
                        # self.log_replayer.seek_time(msg.startTime)
                        # self.log_replayer.loop = msg.loop
                        self.loop = msg.loop
                        self.play_state = msg.autoplay

                if b"/replayd/in/loop/" in latest_msgs:
                    data = latest_msgs[b"/replayd/in/loop/"]
                    with messages.BoolValue.from_bytes(data) as msg:
                        # self.log_replayer.loop = msg.value
                        self.loop = msg.value
                    print(f"loop {self.loop}")

                if b"/replayd/in/start/" in latest_msgs:
                    self.play_state = True
                    print("start")

                if b"/replayd/in/stop/" in latest_msgs:
                    self.play_state = False
                    print("stop")

                if b"/replayd/in/scrub/" in latest_msgs:
                    data = latest_msgs[b"/replayd/in/scrub/"]
                    with messages.Float64Value.from_bytes(data) as msg:
                        self.seek_time(msg.value)

                await asyncio.sleep(0.001)

            except DeepDRRServerException as e:
                print(f"server exception: {e}")
                await pub_socket.send_multipart([b"/server_exception/", e.status_response().to_bytes()])
            
    def seek_time(self, time):
        prev_play_state = self.play_state
        self.play_state = False
        self.log_replayer.seek_time(time)
        self.playback_time = time
        self.play_state = prev_play_state

    async def status_loop(self):
        pub_socket = self.zmq_setup_socket(zmq.PUB, self.pub_port)

        while True:
            if not self.enabled:
                await asyncio.sleep(2)
            await asyncio.sleep(0.2)
            msg = messages.ReplayerStatus.new_message()
            msg.enabled = self.enabled
            msg.playing = self.play_state
            msg.time = self.playback_time if self.playback_time is not None else 0
            # msg.time = self.log_replayer.current_time if self.log_replayer is not None else 0
            msg.logId = self.log_id if self.log_id is not None else ""
            msg.startTime = self.log_replayer.starttime if self.log_replayer is not None else 0
            msg.endTime = self.log_replayer.endtime if self.log_replayer is not None else 0
            msg.loop = self.loop
            # msg.loop = self.log_replayer.loop if self.log_replayer is not None else False
            await pub_socket.send_multipart([b"/replayd/status/", msg.to_bytes()])

            if self.enabled:
                print(f"replayd status: {self.playback_time=}")
                # print(f"replayd status: {self.playback_time=} {msg.playing} {msg.time} {msg.logId} {msg.startTime} {msg.endTime} {msg.loop} {self.log_replayer=} {self.log_time_offset=}")

    async def loglist_loop(self):
        pub_socket = self.zmq_setup_socket(zmq.PUB, self.pub_port)

        while True:
            await asyncio.sleep(5)
            if self.enabled:
                self.invalidate_pathes_sorted_mtime()
                msg = messages.LogList.new_message()
                msg.init('logs', len(self.pathes_sorted_mtime))
                for i, path in enumerate(self.pathes_sorted_mtime):
                    msg.logs[i].id = path.name
                    msg.logs[i].mtime = int(os.path.getmtime(path))
                await pub_socket.send_multipart([b"/replayd/list/", msg.to_bytes()])

    async def replay_loop(self):
        pub_socket = self.zmq_setup_socket(zmq.PUB, self.pub_port)

        print("-"*20)
        i = 0

        def play_condition():
            return self.play_state and self.log_replayer is not None
        
        excluded_prefixes = [b"/loggerd/", b"/replayd/"]
        
        while True:
            while not self.enabled:
                await asyncio.sleep(1)
            while play_condition():
                try:
                    logentry = next(self.log_replayer)
                    self.logentry_valid = True

                    # skip excluded topics
                    if any(logentry.topic.startswith(prefix) for prefix in excluded_prefixes):
                        continue

                    # print("waiting to send message")

                    # sleep until it's time to send the message
                    while play_condition() and self.logentry_valid and self.log_time_offset is not None and time.time() - self.log_time_offset < logentry.logMonoTime:
                        self.playback_time = time.time() - self.log_time_offset
                        await asyncio.sleep(0.001)

                    if not (play_condition() and self.logentry_valid):
                        break
                    
                    self.playback_time = time.time() - self.log_time_offset
                    await pub_socket.send_multipart([logentry.topic, logentry.data])

                    # i+= 1
                    # if i % 100 == 0:
                    # #     # print(f"sent {i} messages")
                    # print(f"playing, current time: {self.log_replayer.current_time}")

                except StopIteration:
                    if self.loop:
                        self.seek_time(self.log_replayer.starttime)
                    else:
                        self.play_state = False
                await asyncio.sleep(0)
            await asyncio.sleep(0.01)
            
    async def blocker_loop(self):
        pub_socket = self.zmq_setup_socket(zmq.PUB, self.pub_port)

        block_list = ["deepdrrd", "timed"]

        while True:
            while not self.enabled:
                await asyncio.sleep(1)
            for block in block_list:
                await pub_socket.send_multipart([f"/{block}/in/block/".encode(), b""])
            await asyncio.sleep(5)

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


# @app.command()
# @unwrap_typer_param
# def main(
#     rep_port=typer.Argument(40120),
#     pub_port=typer.Argument(40121),
#     sub_port=typer.Argument(40122),
# ):
#     print(f"rep_port: {rep_port}")
#     print(f"pub_port: {pub_port}")
#     print(f"sub_port: {sub_port}")

#     vrps_logs_dir_default = Path(r"logs/vrpslogs")
#     vrps_logs_dir = Path(os.environ.get("REPLAY_LOG_DIR", vrps_logs_dir_default)).resolve()
#     print(f"replay vrps_logs_dir: {vrps_logs_dir}")

#     with zmq_no_linger_context(zmq.asyncio.Context()) as context:
#         with LogReplayServer(context, rep_port, pub_port, sub_port, vrps_logs_dir) as time_server:
#             asyncio.run(time_server.start())


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
        with LogReplayServer(context, addr, rep_port, pub_port, sub_port, hwm, vrps_log_dir) as replay_server:
            asyncio.run(replay_server.start())
            

if __name__ == '__main__':
    app()
