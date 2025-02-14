import os
import posixpath as xpath
import unittest

import env

from core import GameArchive
from log import logger
from wwise_hierarchy import RandomSequenceContainer, pack_cntr


class TestCntrParser(unittest.TestCase):

    def test_read_robust(self):
        os.environ["TEST"] = "1"
        files = os.scandir(env.get_data_path())

        for file in files:
            if not file.is_file():
                continue
            name, ext = os.path.splitext(file.path)
            if ext != ".stream":
                continue
            logger.critical(f"Testing {os.path.basename(name)}")
            GameArchive.from_file(name)

    def test_robust(self):
        files = os.scandir(env.get_data_path())

        for file in files:
            if not file.is_file():
                continue
            name, ext = os.path.splitext(file.path)
            if ext != ".stream":
                continue
            logger.critical(f"Testing {os.path.basename(name)}")
            left = GameArchive.from_file(name)
            os.environ["TEST"] = "1"
            right = GameArchive.from_file(name)
            os.environ["TEST"] = "0"

            left_cntrs: dict[int, RandomSequenceContainer] = {}
            for v in left.wwise_banks.values():
                if v.hierarchy == None:
                    continue
                left_cntrs.update({
                    k: v 
                    for k, v in v.hierarchy.entries.items()
                    if isinstance(v, RandomSequenceContainer)
                }) 
            right_cntrs: dict[int, RandomSequenceContainer] = {}
            for v in right.wwise_banks.values():
                if v.hierarchy == None:
                    continue
                right_cntrs.update({
                    k: v 
                    for k, v in v.hierarchy.entries.items()
                    if isinstance(v, RandomSequenceContainer)
                }) 
            for k, v in right_cntrs.items():
                self.assertTrue(k in left_cntrs)
                self.assertEqual(pack_cntr(v), left_cntrs[k].get_data())
