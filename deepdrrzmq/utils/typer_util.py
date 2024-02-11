# source:  https://gitlab.com/boratko/typer-utils
from typing import Callable
import functools
import typer
from typer.models import ParameterInfo

__all__ = ["no_option_conversion", "unwrap_typer_param"]


def no_option_conversion():
    """
    Do not perform any conversion of option names. In particular:
     - do not make them lowercase
     - do not change underscores to hyphens

    (Useful for libraries which may require options to be valid variable names, eg. wandb)
    """
    typer.main.get_command_name = lambda name: name


def unwrap_typer_param(f: Callable):
    """
    Unwraps the default values from typer.Argument or typer.Option to allow function to be called normally.
    See: https://github.com/tiangolo/typer/issues/279
    """

    if f.__defaults__ is None:
        return f

    else:
        patched_defaults = []
        actual_default_observed = False
        for i, value in enumerate(f.__defaults__):
            default_value = value.default if isinstance(value, ParameterInfo) else value

            if default_value != ...:
                actual_default_observed = True
                patched_defaults.append(default_value)
            elif actual_default_observed:
                raise SyntaxError("non-default argument follows default argument")
        f.__defaults__ = tuple(patched_defaults)

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        f.__defaults__ = tuple(patched_defaults)
        return f(*args, **kwargs)

    return wrapper
