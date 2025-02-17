import os
import unittest

from core import GameArchive
from log import logger
from tests.parser_test_common import test_all_archive_sync
from wwise_hierarchy import ActorMixer, HircEntry, LayerContainer, RandomSequenceContainer, Sound, pack_sound
from wwise_hierarchy import pack_rand_seq_cntr


class TestParserIntegration(unittest.TestCase):

    def _test_integration(self, archive: str):
        os.environ["TEST_ACTOR_MIXER"] = "0"
        os.environ["TEST_LAYER"] = "0"
        os.environ["TEST_RAND"] = "0"
        os.environ["TEST_SOUND"] = "0"
        ctrl_group = GameArchive.from_file(archive)
        ctrl_entries: dict[int, HircEntry] = {}
        for bank in ctrl_group.wwise_banks.values():
            if bank.hierarchy == None:
                continue
            ctrl_entries.update({
                hirc_entry_id: hirc_entry
                for hirc_entry_id, hirc_entry in bank.hierarchy.entries.items()
                if hirc_entry.hierarchy_type == 0x02 or
                   hirc_entry.hierarchy_type == 0x05 or 
                   hirc_entry.hierarchy_type == 0x07 or 
                   hirc_entry.hierarchy_type == 0x09
            })


        os.environ["TEST_ACTOR_MIXER"] = "1"
        os.environ["TEST_LAYER"] = "1"
        os.environ["TEST_RAND"] = "1"
        os.environ["TEST_SOUND"] = "1"
        exp_group = GameArchive.from_file(archive)
        exp_entries: dict[int, HircEntry] = {}
        for bank in exp_group.wwise_banks.values():
            if bank.hierarchy == None:
                continue
            exp_entries.update({
                hirc_entry_id: hirc_entry
                for hirc_entry_id, hirc_entry in bank.hierarchy.entries.items()
                if hirc_entry.hierarchy_type == 0x02 or
                   hirc_entry.hierarchy_type == 0x05 or 
                   hirc_entry.hierarchy_type == 0x07 or 
                   hirc_entry.hierarchy_type == 0x09
            })

        for hirc_entry_id, hirc_entry in exp_entries.items():
            self.assertIn(hirc_entry_id, ctrl_entries)
            if isinstance(hirc_entry, Sound):
                self.assertEqual(
                    pack_sound(hirc_entry),
                    ctrl_entries[hirc_entry_id].get_data()
                )
            elif isinstance(hirc_entry, RandomSequenceContainer):
                self.assertEqual(
                    pack_rand_seq_cntr(hirc_entry),
                    ctrl_entries[hirc_entry_id].get_data()
                )
            elif isinstance(hirc_entry, ActorMixer) or \
                 isinstance(hirc_entry, LayerContainer):
                self.assertEqual(
                    hirc_entry.get_data(), ctrl_entries[hirc_entry_id].get_data()
                )
            else:
                raise AssertionError("Irrelevant hierarhcy entry")

    def test_integration(self):
        logger.critical("Running test_integration...")
        test_all_archive_sync(self._test_integration)
