import json
from pathlib import Path


def load_config(config_file):
    """
    Loads configuration from a JSON file.

    Args:
        config_file (str): The path to the configuration file.

    Returns:
        dict: The configuration as a dictionary.
    """
    try:
        with open(config_file, 'r') as file:
            config = json.load(file)
        return config
    except FileNotFoundError:
        raise Exception(f"Configuration file {config_file} not found.")
    except json.JSONDecodeError:
        raise Exception("Error decoding JSON from the configuration file.")


"""
Load the config.json file.
"""
deepdrrzmq_dir = Path(__file__).resolve().parents[1]
config_path = deepdrrzmq_dir / 'config.json'
config = load_config(config_path)
