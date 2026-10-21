import yaml


def load_config():
    data = "timeout: 30\nverbose: true"
    yaml.safe_load(data)
