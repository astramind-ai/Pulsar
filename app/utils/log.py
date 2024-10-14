import logging

from vllm.logger import init_logger


def setup_custom_logger(name):
    # Create a logger
    logger = init_logger(name)
    logger.setLevel(logging.INFO)  # Set the logging level
    logger.propagate = False  # Prevent the log messages from propagating to the root logger

    # Check if handlers already exist to avoid duplicate handlers if function is called multiple times
    if not logger.handlers:
        # Create a console handler
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)  # Set the level for this handler

        # Create a formatter and set it to the handler
        formatter = CustomFormatter()
        handler.setFormatter(formatter)

        # Add the handler to the logger
        logger.addHandler(handler)

    return logger


class CustomFormatter(logging.Formatter):
    grey = "\x1b[38;21m"
    yellow = "\x1b[33;21m"
    red = "\x1b[31;21m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    _FORMAT = "%(levelname)s %(asctime)s %(filename)s:%(lineno)d] %(message)s"
    _DATE_FORMAT = "%m-%d %H:%M:%S"

    COLORS = {
        logging.DEBUG: grey,
        logging.INFO: grey,
        logging.WARNING: yellow,
        logging.ERROR: red,
        logging.CRITICAL: bold_red,
    }

    def format(self, record):
        color = self.COLORS.get(record.levelno, self.grey)  # Default to grey if level no found
        formatter = logging.Formatter(color + self._FORMAT + self.reset, self._DATE_FORMAT)
        return formatter.format(record)


log_config = {  # TODO: fix the uvicorn logger to match the vllm one
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "custom": {
            "()": CustomFormatter,
        },
    },
    "handlers": {
        "default": {
            "formatter": "custom",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        },

    },
    "loggers": {
        "": {
            "uvicorn": {
                "handlers": ["default"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["default"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["default"],
                "level": "INFO",
                "propagate": False,
            },
        }
    }
}
