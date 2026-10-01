import json
import os
import pathlib

_BRIDGE_DIR = pathlib.Path(__file__).resolve().parent.parent
CONFIG_FILE = str(_BRIDGE_DIR / "config.json")

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def save_config(config_data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config_data, f, indent=4)

def get_setting(key, default=None):
    config = load_config()
    return config.get(key, default)

def set_setting(key, value):
    config = load_config()
    config[key] = value
    save_config(config)
