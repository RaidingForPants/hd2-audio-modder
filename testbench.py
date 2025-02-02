import os
import shutil
import unittest

from env import TMP
# from tests.mediautil_test import TestMediaUtil
from tests.mod_test import TestMod


if __name__ == "__main__":
    os.mkdir(TMP)
    unittest.main()
    shutil.rmtree(TMP)
