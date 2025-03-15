import os
import unittest

from tests.parser_test_common import test_all_archive_sync
from core import GameArchive
from log import logger
from wwise_hierarchy import Sound, pack_sound


class TestSoundParser(unittest.TestCase):

    @staticmethod
    def _test_sound_parser_read(archive: str):
        os.environ["TEST_SOUND"] = "1"
        GameArchive.from_file(archive)

    def test_sound_parser_read(self):
        logger.critical("Running test_sound_parser_read...")
        test_all_archive_sync(self._test_sound_parser_read)

    def _test_sound_parser_read_pack(self, archive: str):
        os.environ["TEST_SOUND"] = "0"
        ctrl_group = GameArchive.from_file(archive)
        ctrl_sounds: dict[int, Sound] = {}
        for bank in ctrl_group.wwise_banks.values():
            if bank.hierarchy == None:
                continue
            ctrl_sounds.update({
                hirc_entry_id: hirc_entry
                for hirc_entry_id, hirc_entry in bank.hierarchy.entries.items()
                if isinstance(hirc_entry, Sound)
            }) 

        os.environ["TEST_SOUND"] = "1"
        exp_group = GameArchive.from_file(archive)
        exp_sounds: dict[int, Sound] = {}
        for bank in exp_group.wwise_banks.values():
            if bank.hierarchy == None:
                continue
            exp_sounds.update({
                hirc_entry_id: hirc_entry 
                for hirc_entry_id, hirc_entry in bank.hierarchy.entries.items()
                if isinstance(hirc_entry, Sound)
            }) 

        for exp_sound_id, exp_sound in exp_sounds.items():
            self.assertIn(exp_sound_id, ctrl_sounds)
            self.assertEqual(pack_sound(exp_sound), ctrl_sounds[exp_sound_id].get_data())

    def test_sound_parser_read_pack(self):
        logger.critical("Running test_sound_parser_read_pack...")
        test_all_archive_sync(self._test_sound_parser_read)
