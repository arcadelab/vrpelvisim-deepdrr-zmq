# # replay the log file run this!
# import logging
# import sys
# import traceback
# from deepdrrzmq.manager import main
# from deepdrrzmq.process import PythonProcess


# procs = [
#     PythonProcess("zmqproxyd", "deepdrrzmq.zmqproxyd", watchdog_max_dt=-1),
#     # PythonProcess("deepdrrd", "deepdrrzmq.deepdrrd", watchdog_max_dt=-1),
#     # PythonProcess("patientloaderd", "deepdrrzmq.patientloaderd", watchdog_max_dt=-1),
#     # PythonProcess("timed", "deepdrrzmq.timed", watchdog_max_dt=-1),
#     # PythonProcess("printd", "deepdrrzmq.printd", watchdog_max_dt=-1),
#     # PythonProcess("loggerd", "deepdrrzmq.loggerd", watchdog_max_dt=-1),
#     PythonProcess("replayd", "deepdrrzmq.replayd", watchdog_max_dt=-1),
# ]

# replay_procs = {p.name: p for p in procs}

# if __name__ == "__main__":
#     # set log level
#     logging.basicConfig(level=logging.DEBUG)

#     try:
#         main(replay_procs)
#     except Exception:
#         logging.exception("manager main crashed")
#         traceback.print_exc()
        
    
#     logging.info("manager exit")
#     sys.exit(0)
