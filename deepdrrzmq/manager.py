"""
Manager for deepdrrzmq processes.
Prints a status line for each process every second.

Usage:
    python -m deepdrrzmq.manager
"""
# adapted from https://github.com/commaai/openpilot

import datetime
import os
import signal
import subprocess
import sys
import traceback
from typing import List, Tuple, Union
import logging

from .utils.zmq_util import *
from .process import *


def manager_prepare(managed_processes) -> None:
    for p in managed_processes.values():
        p.prepare()


def manager_cleanup(managed_processes) -> None:
    # send signals to kill all procs
    for p in managed_processes.values():
        p.stop(block=False)

    # ensure all are killed
    for p in managed_processes.values():
        p.stop(block=True)

    logging.info("everything is dead")


def manager_thread(managed_processes) -> None:
    logging.info("manager start")

    with zmq_no_linger_context(zmq.asyncio.Context()) as context:
        ensure_running(managed_processes.values())

        while True:
            ensure_running(managed_processes.values())

            running = ' '.join("%s%s\u001b[0m" % ("\u001b[32m" if p.proc.is_alive() else "\u001b[31m", p.name)
                                            for p in managed_processes.values() if p.proc)
            print(running)

            time.sleep(1)

            # todo: shutdown command
            # shutdown = False

            # if shutdown:
            #         break


def main(managed_processes) -> None:
    manager_prepare(managed_processes)

    # SystemExit on sigterm
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(1))

    try:
        manager_thread(managed_processes)
    except Exception:
        logging.exception("manager crashed")
        traceback.print_exc()
    finally:
        manager_cleanup(managed_processes)


procs = [
    PythonProcess("zmqproxyd", "deepdrrzmq.zmqproxyd", watchdog_max_dt=-1),
    PythonProcess("deepdrrd", "deepdrrzmq.deepdrrd", watchdog_max_dt=-1),
    PythonProcess("patientloaderd", "deepdrrzmq.patientloaderd", watchdog_max_dt=-1),
    PythonProcess("timed", "deepdrrzmq.timed", watchdog_max_dt=-1),
    PythonProcess("snapshotd", "deepdrrzmq.snapshotd", watchdog_max_dt=-1),
    PythonProcess("loggerd", "deepdrrzmq.loggerd", watchdog_max_dt=-1),
    PythonProcess("replayd", "deepdrrzmq.replayd", watchdog_max_dt=-1),
    # PythonProcess("printd", "deepdrrzmq.printd", watchdog_max_dt=-1),
]

main_procs = {p.name: p for p in procs}

if __name__ == "__main__":
    # set log level
    logging.basicConfig(level=logging.DEBUG)

    try:
        main(main_procs)
    except Exception:
        logging.exception("manager main crashed")
        traceback.print_exc()
        
    
    logging.info("manager exit")
    # manual exit because we are forked
    sys.exit(0)
