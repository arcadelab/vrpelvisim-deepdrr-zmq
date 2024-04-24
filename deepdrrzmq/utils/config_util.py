import json
from pathlib import Path


def load_config(config_path):
    """
    Load the JSON configuration file from the given path.    
    
    
    :param config_path: The path to the configuration file.
    :type config_path: str
    """
    
    try:
        with open(config_path, 'r') as file:
            config = json.load(file)
        return config
    except FileNotFoundError:
        raise Exception(f"Configuration file {config_path} not found.")
    except json.JSONDecodeError:
        raise Exception("Error decoding JSON from the configuration file.")


def get_default_config_path():
    """
    Get the default path to the config.json file.
    """
    deepdrrzmq_dir = Path(__file__).resolve().parents[1]
    config_path = deepdrrzmq_dir / 'config.json'
    return config_path


"""
Load the config.json file.
"""
config_path = get_default_config_path()
config = load_config(config_path)
