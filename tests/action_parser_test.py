import os
import unittest

from core import GameArchive
from log import logger
from tests.parser_test_common import test_all_archive_sync
from wwise_hierarchy_154 import HircEntry, Action


class TestActionParser(unittest.TestCase):

    @staticmethod
    def _test_action_read(archive: str):
        os.environ["TEST_ACTION"] = "1"
        GameArchive.from_file(archive)

    def test_action_read(self):
        logger.critical("Running test_action_read...")
        test_all_archive_sync(self._test_action_read)

    def _test_action_read_pack(self, archive: str):
        os.environ["TEST_ACTION"] = "0"
        ctrl_group = GameArchive.from_file(archive)
        ctrl_cntrs: dict[int, HircEntry] = {}
        for bank in ctrl_group.wwise_banks.values():
            if bank.hierarchy == None:
                continue
            ctrl_cntrs.update({
                hirc_entry_id: hirc_entry
                for hirc_entry_id, hirc_entry in bank.hierarchy.entries.items()
                if hirc_entry.hierarchy_type == 0x03
            }) 

        os.environ["TEST_ACTION"] = "1"
        exp_group = GameArchive.from_file(archive)
        exp_cntrs: dict[int, Action] = {}
        for bank in exp_group.wwise_banks.values():
            if bank.hierarchy == None:
                continue
            exp_cntrs.update({
                hirc_entry_id: hirc_entry 
                for hirc_entry_id, hirc_entry in bank.hierarchy.entries.items()
                if isinstance(hirc_entry, Action)
            }) 

        for exp_cntr_id, exp_cntr in exp_cntrs.items():
            self.assertIn(exp_cntr_id, ctrl_cntrs)
            try:
                self.assertEqual(
                    exp_cntr.get_data(), ctrl_cntrs[exp_cntr_id].get_data()
                )
            except:
                raise AssertionError(f"{archive}")

    def test_action_read_pack(self):
        logger.critical("Running test_action_read_pack...")
        test_all_archive_sync(self._test_action_read_pack)
