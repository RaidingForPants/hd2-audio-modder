import os
import pickle

from log import logger


default_path = "setting.pickle"


class Setting:

    def __init__(self, data: str = ""):
        self.data = data

    def save(self, config_path: str = "setting.pickle"):
        """
        @exception
        - OSError
        - pickle.PickleError
        """
        with open(config_path, "wb") as f:
            pickle.dump(self, f)


def load_setting(path: str = default_path) -> Setting:
    """
    @exception
    - OSError
    - pickle.PickleError
    """
    if not os.path.exists(path):
        logger.warning(
            "Failed to locate existing application setting. Creating new one..."
        )

        setting = Setting()
        setting.save()

        logger.info("Created brand new application setting")

        return setting

    with open(path, "rb") as f:
        setting = pickle.load(f)
        if not isinstance(setting, Setting):
            raise ValueError(
                "De-serializing pickle data is not an instance of Setting."
            )

        setting.save()

        return setting
