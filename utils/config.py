"""
Configuration utilities for the IRC bot project.

This module provides functions for loading and saving configuration files in YAML format.
"""
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional

# Set up logging
logger = logging.getLogger(__name__)


def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load a YAML configuration file.

    Args:
        config_path: Path to the YAML configuration file

    Returns:
        dict: The loaded configuration

    Raises:
        FileNotFoundError: If the config file doesn't exist
        yaml.YAMLError: If the YAML is invalid
    """
    path = Path(config_path)
    if not path.exists():
        error_msg = f"Configuration file not found: {path}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    try:
        with open(path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)

        if not isinstance(config, dict):
            logger.warning("Configuration file %s is empty or invalid", path)
            config = {}

        logger.info("Loaded configuration from %s", path)
        return config

    except yaml.YAMLError as err:
        logger.error("Error parsing YAML configuration file %s: %s", path, err)
        raise
    except Exception as err:
        logger.error("Unexpected error loading configuration from %s: %s", path, err)
        raise


def save_config(config: Dict[str, Any], config_path: str) -> None:
    """
    Save a configuration dictionary to a YAML file.

    Args:
        config: Configuration dictionary to save
        config_path: Path to save the configuration to

    Raises:
        OSError: If there's an error writing to the file
    """
    path = Path(config_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as file:
            yaml.safe_dump(config, file, default_flow_style=False)
        logger.info("Saved configuration to %s", path)
    except Exception as err:
        logger.error("Error saving configuration to %s: %s", path, err)
        raise
