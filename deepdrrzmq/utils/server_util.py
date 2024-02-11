
import capnp
import typer
import zmq.asyncio
import os

file_path = os.path.dirname(os.path.realpath(__file__))
messages = capnp.load(os.path.join(file_path, "..", 'messages.capnp'))

def make_response(code, message):
    """
    Create a StatusResponse message with the given code and message.

    :param code: The status code.
    :param message: The status message.
    :return: The StatusResponse message.
    """
    response = messages.StatusResponse.new_message()
    response.code = code
    response.message = message
    return response

def capnp_optional(optional):
    """
    Convert a capnp optional to a python value.
    
    :param optional: The capnp optional.
    :return: The value of the optional, or None if the optional is not set.
    """
    if optional.which() == "value":
        return optional.value
    else:
        return None

def capnp_square_matrix(optional):
    """
    Convert a capnp optional to a square numpy array.
    
    :param optional: The capnp optional.
    :return: The value of the optional, or None if the optional is not set.
    """
    if len(optional.data) == 0:
        return None
    else:
        arr = np.array(optional.data)
        size = len(arr)
        side = int(size ** 0.5)
        assert size == side ** 2, f"expected square matrix, got {size} elements"
        arr = arr.reshape((side, side))
        return arr

class DeepDRRServerException(Exception):
    """
    Exception class for server errors.
    """
    def __init__(self, code, message, subexception=None):
        """
        :param code: The status code.
        :param message: The status message.
        """
        self.code = code
        self.message = message
        self.subexception = subexception

    def __str__(self):
        return f"DeepDRRServerError({self.code}, {self.message})"

    def status_response(self):
        return make_response(self.code, self.message)
    