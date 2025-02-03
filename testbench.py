import os
import shutil
import unittest

from env import TMP
# from tests.mediautil_test import TestMediaUtil
# from tests.mod_test import TestMod
from tests.sound_handler_test import TestSoundHandler


if __name__ == "__main__":
    if os.path.exists(TMP):
        shutil.rmtree(TMP)
    os.mkdir(TMP)
    unittest.main()
