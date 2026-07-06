"""Logging setup for the ETL pipeline: console + append-only log file."""

import logging
import os

import config


def get_logger(name: str = "etl") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    os.makedirs(os.path.dirname(config.LOG_PATH), exist_ok=True)

    file_handler = logging.FileHandler(config.LOG_PATH, mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
