import logging


default_formatter = logging.Formatter(
    "{time:\"%(asctime)s\","
    "level:\"%(levelname)s\","
    "filename:\"%(filename)s\","
    "function:\"%(funcName)s\"," 
    "lineno:%(lineno)d,"
    "msg:\"%(message)s\"}"
)

default_file_handler = logging.FileHandler("log.txt")
default_file_handler.setFormatter(default_formatter)

default_stream_handler = logging.StreamHandler()
default_stream_handler.setFormatter(default_formatter)


def get_logger():
    logger: logging.Logger | None = None

    def _get_logger():
        nonlocal logger
        if logger != None:
            return logger

        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)
        
        logger.addHandler(default_file_handler)
        logger.addHandler(default_stream_handler)

        return logger

    return _get_logger


logger = get_logger()()
