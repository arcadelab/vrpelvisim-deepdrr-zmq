import time
import signal


def main():
    # don't quit on sigterm or keyboard interrupt
    signal.signal(signal.SIGTERM, lambda signum, frame: print("SIGTERM"))
    signal.signal(signal.SIGINT, lambda signum, frame: print("SIGINT"))


    while True:
        print("Hello World!")
        time.sleep(2)

if __name__ == "__main__":
    main()