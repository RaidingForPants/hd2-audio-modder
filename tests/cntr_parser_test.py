import os
import posixpath as xpath
import unittest

import env

from core import GameArchive
from log import logger
from concurrent.futures import ProcessPoolExecutor as Pool, Future
from wwise_hierarchy import HircEntry, LayerContainer, RandomSequenceContainer, pack_rand_seq_cntr


class TestCntrParser(unittest.TestCase):

    def test_rand_seq_read(self):
        os.environ["TEST_RAND"] = "0"
        os.environ["TEST_LAYER"] = "0"
        files = os.scandir(env.get_data_path())

        def task(archive: str):


        with Pool(8) as p:
            tests: list[tuple[str, Future]] = []
            for file in files:
                if not file.is_file():
                    continue
                archive, ext = os.path.splitext(file.path)
                if ext != ".stream":
                    continue
                os.environ["TEST_RAND"] = "1"
                tests.append((archive, p.submit(GameArchive.from_file, archive)))

            finished = 0
            while finished < len(tests):
                for test in tests:
                    if not test[1].done():
                        continue
                    finished += 1
                    err = test[1].exception()
                    if err != None:
                        logger.critical(f"test_rand_seq_read: {os.path.basename(test[0])} failed")

    def test_rand_seq_read_pack(self):
        os.environ["TEST_RAND"] = "0"
        os.environ["TEST_LAYER"] = "0"

        files = os.scandir(env.get_data_path())

        def task(name: str):
            os.environ["TEST_RAND"] = "0"
            ctrl_group = GameArchive.from_file(name)

            os.environ["TEST_RAND"] = "1"
            exp_group = GameArchive.from_file(name)

            ctrl_cntrs: dict[int, RandomSequenceContainer] = {}
            for bank in ctrl_group.wwise_banks.values():
                if bank.hierarchy == None:
                    continue
                ctrl_cntrs.update({
                    hirc_entry_id: hirc_entry
                    for hirc_entry_id, hirc_entry in bank.hierarchy.entries.items()
                    if isinstance(hirc_entry, RandomSequenceContainer)
                }) 

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
                if exp_cntr_id not in ctrl_cntrs:
                    raise AssertionError(
                        f"{exp_cntr_id} is not in control group container."
                    )
                if pack_rand_seq_cntr(exp_cntr) != ctrl_cntrs[exp_cntr_id].get_data():
                    raise AssertionError("diffing fail")

        with Pool(8) as p:
            tests: list[tuple[str, Future]] = []

            for file in files:
                if not file.is_file():
                    continue
                name, ext = os.path.splitext(file.path)
                if ext != ".stream":
                    continue
                tests.append((name, p.submit(task, name)))

            finished = 0
            while finished < len(tests):
                for test in tests:
                    if not test[1].done():
                        continue
                    finished += 1
                    err = test[1].exception()
                    if err != None:
                        logger.critical(f"test_rand_seq_read_pack: {os.path.basename(test[0])} fail")


    def test_layer_read(self):
        os.environ["TEST_RAND"] = "0"
        os.environ["TEST_LAYER"] = "0"

        files = os.scandir(env.get_data_path())

        for file in files:
            if not file.is_file():
                continue
            name, ext = os.path.splitext(file.path)
            if ext != ".stream":
                continue
            os.environ["TEST_LAYER"] = "1"
            GameArchive.from_file(name)

    def test_layer_pack(self):
        os.environ["TEST_RAND"] = "0"
        os.environ["TEST_LAYER"] = "0"

        files = os.scandir(env.get_data_path())

        for file in files:
            if not file.is_file():
                continue
            name, ext = os.path.splitext(file.path)
            if ext != ".stream":
                continue

            os.environ["TEST_LAYER"] = "0"
            ctrl_group = GameArchive.from_file(name)

            os.environ["TEST_LAYER"] = "1"
            exp_group = GameArchive.from_file(name)

            ctrl_cntrs: dict[int, HircEntry] = {}
            for bank in ctrl_group.wwise_banks.values():
                if bank.hierarchy == None:
                    continue
                ctrl_cntrs.update({
                    hirc_entry_id: hirc_entry
                    for hirc_entry_id, hirc_entry in bank.hierarchy.entries.items()
                    if hirc_entry.hierarchy_type == 0x09
                }) 

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
                self.assertTrue(exp_cntr_id in ctrl_cntrs)
                self.assertEqual(exp_cntr.get_data(), ctrl_cntrs[exp_cntr_id].get_data())

    def test_integration(self):
        os.environ["TEST_RAND"] = "0"
        os.environ["TEST_LAYER"] = "0"

        files = os.scandir(env.get_data_path())

        for file in files:
            if not file.is_file():
                continue
            name, ext = os.path.splitext(file.path)
            if ext != ".stream":
                continue

            os.environ["TEST_RAND"] = "0"
            os.environ["TEST_LAYER"] = "0"
            ctrl_group = GameArchive.from_file(name)

            os.environ["TEST_RAND"] = "1"
            os.environ["TEST_LAYER"] = "1"
            exp_group = GameArchive.from_file(name)

            ctrl_cntrs: dict[int, HircEntry] = {}
            for bank in ctrl_group.wwise_banks.values():
                if bank.hierarchy == None:
                    continue
                ctrl_cntrs.update({
                    hirc_entry_id: hirc_entry
                    for hirc_entry_id, hirc_entry in bank.hierarchy.entries.items()
                    if hirc_entry.hierarchy_type == 0x05 or hirc_entry.hierarchy_type == 0x09
                }) 

            exp_cntrs: dict[int, HircEntry] = {}
            for bank in exp_group.wwise_banks.values():
                if bank.hierarchy == None:
                    continue
                exp_cntrs.update({
                    hirc_entry_id: hirc_entry 
                    for hirc_entry_id, hirc_entry in bank.hierarchy.entries.items()
                    if hirc_entry.hierarchy_type == 0x09 or hirc_entry.hierarchy_type == 0x05
                }) 

            for exp_cntr_id, exp_cntr in exp_cntrs.items():
                self.assertTrue(exp_cntr_id in ctrl_cntrs)
                if exp_cntr.hierarchy_type == 0x05:
                    self.assertEqual(pack_rand_seq_cntr(exp_cntr), ctrl_cntrs[exp_cntr_id].get_data())
                elif exp_cntr.hierarchy_type == 0x09:
                    self.assertEqual(exp_cntr.get_data(), ctrl_cntrs[exp_cntr_id].get_data())
                else:
                    raise AssertionError()
