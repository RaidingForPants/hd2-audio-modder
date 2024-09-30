import logging

def get_logger():
    logger: logging.Logger | None = None

    def _get_logger():
        nonlocal logger
        if logger != None:
            return logger
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)
        
        file_handler = logging.FileHandler("log.txt")
        stderr_handler = logging.StreamHandler()

        formatter = logging.Formatter("{time:\"%(asctime)s\","
                                        "level:\"%(levelname)s\","
                                        "filename:\"%(filename)s\","
                                        "function:\"%(funcName)s\"," 
                                        "lineno:%(lineno)d,"
                                        "msg:\"%(message)s\"}")

        file_handler.setFormatter(formatter)
        stderr_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(stderr_handler)

        return logger

    return _get_logger

logger = get_logger()()
