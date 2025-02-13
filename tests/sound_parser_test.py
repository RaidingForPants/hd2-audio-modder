import os
import posixpath as xpath
import unittest

import env

from core import GameArchive
from log import logger
from wwise_hierarchy import Sound, pack_sound


class TestSoundParser(unittest.TestCase):

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
            os.environ["TEST_FLAG"] = "True"
            right = GameArchive.from_file(name)
            os.environ["TEST_FLAG"] = "False"

            left_sounds: dict[int, Sound] = {}
            for v in left.wwise_banks.values():
                if v.hierarchy == None:
                    continue
                left_sounds.update({
                    k: v 
                    for k, v in v.hierarchy.entries.items()
                    if isinstance(v, Sound)
                }) 
            right_sounds: dict[int, Sound] = {}
            for v in right.wwise_banks.values():
                if v.hierarchy == None:
                    continue
                right_sounds.update({
                    k: v 
                    for k, v in v.hierarchy.entries.items()
                    if isinstance(v, Sound)
                }) 
            for k, v in right_sounds.items():
                self.assertTrue(k in left_sounds)
                self.assertEqual(pack_sound(v), left_sounds[k].get_data())
                    

    def test_edge_case(self):
        files = [
            "04f60fc9a8eec97d",
        ]
        for file in files:
            logger.critical(f"Testing {file}")
            left = GameArchive.from_file(xpath.join(env.get_data_path(), file))
            os.environ["TEST_FLAG"] = "True"
            right = GameArchive.from_file(xpath.join(env.get_data_path(), file))
            os.environ["TEST_FLAG"] = "False"

            left_sounds: dict[int, Sound] = {}
            for v in left.wwise_banks.values():
                if v.hierarchy == None:
                    continue
                left_sounds.update({
                    k: v 
                    for k, v in v.hierarchy.entries.items()
                    if isinstance(v, Sound)
                }) 
            right_sounds: dict[int, Sound] = {}
            for v in right.wwise_banks.values():
                if v.hierarchy == None:
                    continue
                right_sounds.update({
                    k: v 
                    for k, v in v.hierarchy.entries.items()
                    if isinstance(v, Sound)
                }) 
            for k, v in right_sounds.items():
                self.assertTrue(k in left_sounds)
                self.assertEqual(pack_sound(v), left_sounds[k].get_data())
