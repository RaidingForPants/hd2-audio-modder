import os
import unittest

from core import GameArchive
from log import logger
from tests.parser_test_common import test_all_archive_sync
from wwise_hierarchy import HircEntry, LayerContainer, RandomSequenceContainer 
from wwise_hierarchy import pack_rand_seq_cntr


class TestCntrParser(unittest.TestCase):

    @staticmethod
    def _test_rand_seq_read(archive: str):
        os.environ["TEST_RAND"] = "1"
        GameArchive.from_file(archive)

    def test_rand_seq_read(self):
        logger.critical("Running test_rand_seq_read...")
        test_all_archive_sync(self._test_rand_seq_read)
        # test_all_archive_multi_process(self._test_rand_seq_read, "test_rand_seq_read")

    def _test_rand_seq_read_pack(self, archive: str):
        os.environ["TEST_RAND"] = "0"
        ctrl_group = GameArchive.from_file(archive)
        ctrl_cntrs: dict[int, RandomSequenceContainer] = {}
        for bank in ctrl_group.wwise_banks.values():
            if bank.hierarchy == None:
                continue
            ctrl_cntrs.update({
                hirc_entry_id: hirc_entry
                for hirc_entry_id, hirc_entry in bank.hierarchy.entries.items()
                if isinstance(hirc_entry, RandomSequenceContainer)
            }) 

        os.environ["TEST_RAND"] = "1"
        exp_group = GameArchive.from_file(archive)
        exp_cntrs: dict[int, RandomSequenceContainer] = {}
        for bank in exp_group.wwise_banks.values():
            if bank.hierarchy == None:
                continue
            exp_cntrs.update({
                hirc_entry_id: hirc_entry 
                for hirc_entry_id, hirc_entry in bank.hierarchy.entries.items()
                if isinstance(hirc_entry, RandomSequenceContainer)
            }) 

        for exp_cntr_id, exp_cntr in exp_cntrs.items():
            self.assertIn(exp_cntr_id, ctrl_cntrs)
            self.assertEqual(
                pack_rand_seq_cntr(exp_cntr), ctrl_cntrs[exp_cntr_id].get_data()
            )

    def test_rand_seq_read_pack(self):
        logger.critical("Running test_rand_seq_read_pack...")
        test_all_archive_sync(self._test_rand_seq_read_pack)
        # test_all_archive_multi_process(self._test_rand_seq_read_pack, "test_rand_seq_read_pack")

    @staticmethod
    def _test_layer_read(archive: str):
        os.environ["TEST_LAYER"] = "1"
        GameArchive.from_file(archive)

    def test_layer_read(self):
        logger.critical("Running test_layer_read...")
        test_all_archive_sync(self._test_layer_read)
        # test_all_archive_multi_process(self._test_layer_read, "test_layer_read")

    def _test_layer_read_pack(self, archive: str):
        os.environ["TEST_LAYER"] = "0"
        ctrl_group = GameArchive.from_file(archive)
        ctrl_cntrs: dict[int, HircEntry] = {}
        for bank in ctrl_group.wwise_banks.values():
            if bank.hierarchy == None:
                continue
            ctrl_cntrs.update({
                hirc_entry_id: hirc_entry
                for hirc_entry_id, hirc_entry in bank.hierarchy.entries.items()
                if hirc_entry.hierarchy_type == 0x09 
            }) 

        os.environ["TEST_LAYER"] = "1"
        exp_group = GameArchive.from_file(archive)
        exp_cntrs: dict[int, HircEntry] = {}
        for bank in exp_group.wwise_banks.values():
            if bank.hierarchy == None:
                continue
            exp_cntrs.update({
                hirc_entry_id: hirc_entry 
                for hirc_entry_id, hirc_entry in bank.hierarchy.entries.items()
                if hirc_entry.hierarchy_type == 0x09 
            }) 

        for exp_cntr_id, exp_cntr in exp_cntrs.items():
            self.assertIn(exp_cntr_id, ctrl_cntrs)
            self.assertTrue(isinstance(exp_cntr, LayerContainer))
            self.assertEqual(
                exp_cntr.get_data(), ctrl_cntrs[exp_cntr_id].get_data()
            )

    def test_layer_read_pack(self):
        logger.critical("Running test_layer_read_pack...")
        test_all_archive_sync(self._test_layer_read_pack)
        # test_all_archive_multi_process(self._test_layer_read_pack, "test_layer_read_pack")

    def _test_rand_layer_read_pack(self, archive: str):
        os.environ["TEST_RAND"] = "0"
        os.environ["TEST_LAYER"] = "0"
        ctrl_group = GameArchive.from_file(archive)
        ctrl_cntrs: dict[int, HircEntry] = {}
        for bank in ctrl_group.wwise_banks.values():
            if bank.hierarchy == None:
                continue
            ctrl_cntrs.update({
                hirc_entry_id: hirc_entry
                for hirc_entry_id, hirc_entry in bank.hierarchy.entries.items()
                if hirc_entry.hierarchy_type == 0x05 or 
                   hirc_entry.hierarchy_type == 0x09
            }) 

        os.environ["TEST_RAND"] = "1"
        os.environ["TEST_LAYER"] = "1"
        exp_group = GameArchive.from_file(archive)
        exp_cntrs: dict[int, HircEntry] = {}
        for bank in exp_group.wwise_banks.values():
            if bank.hierarchy == None:
                continue
            exp_cntrs.update({
                hirc_entry_id: hirc_entry 
                for hirc_entry_id, hirc_entry in bank.hierarchy.entries.items()
                if hirc_entry.hierarchy_type == 0x05 or 
                   hirc_entry.hierarchy_type == 0x09
            }) 

        for exp_cntr_id, exp_cntr in exp_cntrs.items():
            self.assertIn(exp_cntr_id, ctrl_cntrs)
            if isinstance(exp_cntr, RandomSequenceContainer):
                self.assertEqual(
                    pack_rand_seq_cntr(exp_cntr),
                    ctrl_cntrs[exp_cntr_id].get_data()
                )
            elif isinstance(exp_cntr, LayerContainer):
                self.assertEqual(
                    exp_cntr.get_data(), ctrl_cntrs[exp_cntr_id].get_data()
                )
            else:
                raise AssertionError("Irrelevant hierarhcy entry")

    def test_rand_layer_read_pack(self):
        logger.critical("Running test_rand_layer_read_pack...")
        test_all_archive_sync(self._test_rand_layer_read_pack)
        # test_all_archive_multi_process(self._test_integration, "TestCntrParser.test_integration")
