import zmq
import zmq.asyncio
from contextlib import contextmanager


@contextmanager
def zmq_no_linger_context(context):
    try:
        yield context
    finally:
        context.destroy(linger=0)


async def zmq_poll_latest(sub_socket, max_skip=1000, no_drop_topics=None):
    """
    Polls the latest messages from a zmq socket.
    
    :param sub_socket: the socket to poll
    :param max_skip: the maximum number of messages to skip
    :param no_drop_topics: a list of topics that should not be dropped
    :return: a dictionary mapping topics to messages
    """
    latest_msgs = {}

    # wait until receiving a message, FIFO
    topic, data = await sub_socket.recv_multipart()
    latest_msgs[topic] = data

    if no_drop_topics is not None and topic in no_drop_topics:
        return latest_msgs

    # process messages that are queued up
    try:
        for i in range(max_skip):
            topic, data = await sub_socket.recv_multipart(flags=zmq.NOBLOCK)
            latest_msgs[topic] = data
            
            if no_drop_topics is not None and topic in no_drop_topics:
                return latest_msgs
    except zmq.ZMQError:
        pass

    return latest_msgs