"""Resolve machine-local paths without assuming an OZtree checkout layout."""

import configparser
import os
from pathlib import Path


def local_config_path():
    config_path = os.environ.get("TREE_BUILD_CONFIG")
    if config_path is None:
        return Path.cwd() / "config.ini"
    path = Path(config_path).expanduser()
    if not config_path.strip() or not path.is_absolute():
        raise ValueError("TREE_BUILD_CONFIG must be an absolute path to the configuration file.")
    return path


def resolve_path(explicit_path, setting, option):
    """Resolve a CLI path or a path from the machine-local [onezoom] section."""
    if explicit_path is not None:
        if not str(explicit_path).strip():
            raise ValueError(f"{option} must not be empty")
        return str(Path(explicit_path).expanduser())

    config_path = local_config_path()
    config = configparser.ConfigParser(interpolation=None)
    if config_path.exists() or "TREE_BUILD_CONFIG" in os.environ:
        with config_path.open(encoding="utf-8") as config_file:
            config.read_file(config_file)
    value = config.get("onezoom", setting, fallback="").strip()
    if not value:
        raise ValueError(f"Specify {option} or set [onezoom] {setting} in {config_path}.")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = config_path.parent / path
    return str(path)
