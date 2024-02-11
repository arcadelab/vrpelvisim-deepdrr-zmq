"""
Process manager helper classes with auto-restart watchdogs.
"""
# adapted from https://github.com/commaai/openpilot

import importlib
import os
import signal
import struct
import time
import subprocess
from typing import Optional, Callable, List, ValuesView, Dict
from abc import ABC, abstractmethod
from multiprocessing import Process, get_context
import logging

from .basedir import BASEDIR

ENABLE_WATCHDOG = os.getenv("NO_WATCHDOG") is None

def launcher(proc: str, name: str) -> None:
  try:
    # import the process
    mod = importlib.import_module(proc)

    # exec the process
    getattr(mod, 'main')()
  except KeyboardInterrupt:
    logging.warning(f"child {proc} got SIGINT")
  except Exception:
    raise

def nativelauncher(pargs: List[str], cwd: str, name: str) -> None:
  os.environ['MANAGER_DAEMON'] = name

  # exec the process
  os.chdir(cwd)
  os.execvp(pargs[0], pargs)

def join_process(process: Process, timeout: float) -> None:
  t = time.monotonic()
  while time.monotonic() - t < timeout and process.exitcode is None:
    time.sleep(0.001)


class ManagerProcess(ABC):
  unkillable = False
  daemon = False
  sigkill = False
  proc: Optional[Process] = None
  enabled = True
  name = ""

  last_watchdog_time = 0
  watchdog_max_dt: Optional[int] = None
  watchdog_seen = False
  shutting_down = False

  @abstractmethod
  def prepare(self) -> None:
    pass

  @abstractmethod
  def start(self) -> None:
    pass

  def restart(self) -> None:
    self.stop()
    self.start()

  def check_watchdog(self, last_watchdog_time: Optional[float]) -> None:
    if self.watchdog_max_dt is None or self.proc is None:
      return

    if last_watchdog_time is not None:
      self.last_watchdog_time = last_watchdog_time

    dt = time.time() - self.last_watchdog_time / 1e9

    if not self.proc.is_alive() and ENABLE_WATCHDOG:
        logging.error(f"Process died {self.name} (exitcode {self.proc.exitcode}) restarting")
        self.restart()

    if dt > self.watchdog_max_dt:
      if self.watchdog_seen and ENABLE_WATCHDOG:
        logging.error(f"Watchdog timeout for {self.name} (exitcode {self.proc.exitcode}) restarting")
        self.restart()
    else:
      self.watchdog_seen = True

  def stop(self, retry: bool=True, block: bool=True) -> Optional[int]:
    if self.proc is None:
      return None

    if self.proc.exitcode is None:
      if not self.shutting_down:
        sig = signal.SIGKILL if self.sigkill else signal.SIGINT
        self.signal(sig)
        self.shutting_down = True

        if not block:
          return None

      join_process(self.proc, 5)

      # If process failed to die send SIGKILL or reboot
      if self.proc.exitcode is None and retry:
        logging.info(f"killing {self.name} with SIGKILL")
        self.signal(signal.SIGKILL)
        self.proc.join()

    ret = self.proc.exitcode
    logging.info(f"{self.name} is dead with {ret}")

    if self.proc.exitcode is not None:
      self.shutting_down = False
      self.proc = None

    return ret

  def signal(self, sig: int) -> None:
    if self.proc is None:
      return

    # Don't signal if already exited
    if self.proc.exitcode is not None and self.proc.pid is not None:
      return

    # Can't signal if we don't have a pid
    if self.proc.pid is None:
      return

    logging.info(f"sending signal {sig} to {self.name}")
    os.kill(self.proc.pid, sig)


class NativeProcess(ManagerProcess):
  def __init__(self, name, cwd, cmdline, enabled=True, sigkill=False, watchdog_max_dt=None):
    self.name = name
    self.cwd = cwd
    self.cmdline = cmdline
    self.enabled = enabled
    self.sigkill = sigkill
    self.watchdog_max_dt = watchdog_max_dt

  def prepare(self) -> None:
    pass

  def start(self) -> None:
    # In case we only tried a non blocking stop we need to stop it before restarting
    if self.shutting_down:
      self.stop()

    if self.proc is not None:
      return

    cwd = os.path.join(BASEDIR, self.cwd)
    logging.info(f"starting process {self.name}")
    self.proc = Process(name=self.name, target=nativelauncher, args=(self.cmdline, cwd, self.name))
    self.proc.start()
    self.watchdog_seen = False
    self.shutting_down = False


class PythonProcess(ManagerProcess):
  def __init__(self, name, module, enabled=True, sigkill=False, watchdog_max_dt=None):
    self.name = name
    self.module = module
    self.enabled = enabled
    self.sigkill = sigkill
    self.watchdog_max_dt = watchdog_max_dt

  def prepare(self) -> None:
    if self.enabled:
      logging.info(f"preimporting {self.module}")
      importlib.import_module(self.module)

  def start(self) -> None:
    # In case we only tried a non blocking stop we need to stop it before restarting
    if self.shutting_down:
      self.stop()

    if self.proc is not None:
      return

    logging.info(f"starting python {self.module}")
    self.proc = get_context('spawn').Process(name=self.name, target=launcher, args=(self.module, self.name))
    self.proc.start()
    self.watchdog_seen = False
    self.shutting_down = False


def ensure_running(procs: List[ManagerProcess],
                   not_run: Optional[List[str]]=None,
                   last_watchdog_times: Dict[str, float] = None) -> None:
  if not_run is None:
    not_run = []

  if last_watchdog_times is None:
    last_watchdog_times = {}

  for p in procs:
    run = p.enabled

    run = run and not any((
      p.name in not_run,
    ))

    if run:
      p.start()
    else:
      p.stop(block=False)

    p.check_watchdog(last_watchdog_times.get(p.name, None))