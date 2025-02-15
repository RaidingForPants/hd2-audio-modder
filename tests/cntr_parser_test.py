import functools
import os
import posixpath as xpath
import unittest

import env

from core import GameArchive
from log import logger
from concurrent.futures import ProcessPoolExecutor as Pool, Future
from wwise_hierarchy import HircEntry, LayerContainer, RandomSequenceContainer, pack_rand_seq_cntr


class TestCntrParser(unittest.TestCase):

    @staticmethod
    def _test_rand_seq_read(archive: str):
        os.environ["TEST_RAND"] = "1"
        GameArchive.from_file(archive)

    def test_rand_seq_read(self):
        os.environ["TEST_RAND"] = "0"
        os.environ["TEST_LAYER"] = "0"
        files = os.scandir(env.get_data_path())

        with Pool(8) as p:
            tests: list[tuple[str, Future]] = []
            for file in files:
                if not file.is_file():
                    continue
                archive, ext = os.path.splitext(file.path)
                if ext != ".stream":
                    continue
                binding = functools.partial(self._test_rand_seq_read, archive)
                tests.append((os.path.basename(archive), p.submit(binding)))

            finished_tests_count = 0
            failed_tests: list[tuple[str, BaseException]] = []
            while finished_tests_count < len(tests):
                for test in tests:
                    if not test[1].done():
                        continue
                    finished_tests_count += 1
                    err = test[1].exception()
                    if err != None:
                        failed_tests.append((os.path.basename(test[0]), err))

            if len(failed_tests) > 0:
                logger.critical("There are failed tests in test_rand_seq_read.")
                for failed_test in failed_tests:
                    logger.critical(f"{failed_test[0]}: {failed_test[1]}")

    @staticmethod
    def _test_rand_seq_read_pack(archive: str):
        os.environ["TEST_RAND"] = "0"
        ctrl_group = GameArchive.from_file(archive)

        os.environ["TEST_RAND"] = "1"
        exp_group = GameArchive.from_file(archive)

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
                    f"Random / Sequence container {exp_cntr_id} is not in "
                     "control group container."
                )
            if pack_rand_seq_cntr(exp_cntr) != ctrl_cntrs[exp_cntr_id].get_data():
                raise AssertionError("diffing fail")

    def test_rand_seq_read_pack(self):
        os.environ["TEST_RAND"] = "0"
        os.environ["TEST_LAYER"] = "0"

        files = os.scandir(env.get_data_path())

        with Pool(8) as p:
            tests: list[tuple[str, Future]] = []

            for file in files:
                if not file.is_file():
                    continue
                archive, ext = os.path.splitext(file.path)
                if ext != ".stream":
                    continue
                binding = functools.partial(self._test_rand_seq_read_pack, archive)
                tests.append((os.path.basename(archive), p.submit(binding)))

            finished_tests_count = 0
            failed_tests: list[tuple[str, BaseException]] = []
            while finished_tests_count < len(tests):
                for test in tests:
                    if not test[1].done():
                        continue
                    finished_tests_count += 1
                    err = test[1].exception()
                    if err != None:
                        failed_tests.append((os.path.basename(test[0]), err))

            if len(failed_tests) > 0:
                logger.critical("There are failed tests in test_rand_seq_read_pack.")
                for failed_test in failed_tests:
                    logger.critical(f"{failed_test[0]}: {failed_test[1]}")

    @staticmethod
    def _test_layer_read(archive: str):
        os.environ["TEST_LAYER"] = "1"
        GameArchive.from_file(archive)

    def test_layer_read(self):
        os.environ["TEST_RAND"] = "0"
        os.environ["TEST_LAYER"] = "0"

        files = os.scandir(env.get_data_path())

        with Pool(8) as p:
            tests: list[tuple[str, Future]] = []
            for file in files:
                if not file.is_file():
                    continue
                archive, ext = os.path.splitext(file.path)
                if ext != ".stream":
                    continue
                binding = functools.partial(self._test_layer_read, archive)
                tests.append((archive, p.submit(binding)))

            finished_tests_count = 0
            failed_tests: list[tuple[str, BaseException]] = []
            while finished_tests_count < len(tests):
                for test in tests:
                    if not test[1].done():
                        continue
                    finished_tests_count += 1
                    err = test[1].exception()
                    if err != None:
                        failed_tests.append((os.path.basename(test[0]), err))

            if len(failed_tests) > 0:
                logger.critical("There are failed tests in test_layer_read.")
                for failed_test in failed_tests:
                    logger.critical(f"{failed_test[0]}: {failed_test[1]}")

    @staticmethod
    def _test_layer_read_pack(archive: str):
        os.environ["TEST_LAYER"] = "0"
        ctrl_group = GameArchive.from_file(archive)

        os.environ["TEST_LAYER"] = "1"
        exp_group = GameArchive.from_file(archive)

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
            if exp_cntr_id not in ctrl_cntrs:
                raise AssertionError(
                    f"Layer container {exp_cntr_id} is not in control group "
                     "container."
                )
            if exp_cntr.get_data() !=  ctrl_cntrs[exp_cntr_id].get_data():
                raise AssertionError("diffing fail")

    def test_layer_read_pack(self):
        os.environ["TEST_RAND"] = "0"
        os.environ["TEST_LAYER"] = "0"

        files = os.scandir(env.get_data_path())

        with Pool(8) as p:
            tests: list[tuple[str, Future]] = []
            for file in files:
                if not file.is_file():
                    continue
                archive, ext = os.path.splitext(file.path)
                if ext != ".stream":
                    continue
                binding = functools.partial(self._test_layer_read_pack, archive)
                tests.append((os.path.basename(archive), p.submit(binding)))

            finished_tests_count = 0
            failed_tests: list[tuple[str, BaseException]] = []
            while finished_tests_count < len(tests):
                for test in tests:
                    if not test[1].done():
                        continue
                    finished_tests_count += 1
                    err = test[1].exception()
                    if err != None:
                        failed_tests.append((os.path.basename(test[0]), err))

            if len(failed_tests) > 0:
                logger.critical("There are failed tests in test_layer_read_pack.")
                for failed_test in failed_tests:
                    logger.critical(f"{failed_test[0]}: {failed_test[1]}")

    @staticmethod
    def _test_integration(archive: str):
        os.environ["TEST_RAND"] = "0"
        os.environ["TEST_LAYER"] = "0"
        ctrl_group = GameArchive.from_file(archive)

        os.environ["TEST_RAND"] = "1"
        os.environ["TEST_LAYER"] = "1"
        exp_group = GameArchive.from_file(archive)

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
            if exp_cntr_id not in ctrl_cntrs:
                raise AssertionError(
                    f"Container {exp_cntr_id} is not in control group."
                )
            if exp_cntr.hierarchy_type == 0x05:
                if pack_rand_seq_cntr(exp_cntr) != ctrl_cntrs[exp_cntr_id].get_data():
                    raise AssertionError("Random / Sequence container diffing failed.")
            elif exp_cntr.hierarchy_type == 0x09:
                if exp_cntr.get_data() != ctrl_cntrs[exp_cntr_id].get_data():
                    raise AssertionError("Layer container diffing failed.")
            else:
                raise AssertionError("Irrelevant hierarhcy entry")

    def test_integration(self):
        os.environ["TEST_RAND"] = "0"
        os.environ["TEST_LAYER"] = "0"

        files = os.scandir(env.get_data_path())

        with Pool(8) as p:
            tests: list[tuple[str, Future]] = []
            for file in files:
                if not file.is_file():
                    continue
                archive, ext = os.path.splitext(file.path)
                if ext != ".stream":
                    continue
                binding = functools.partial(self._test_integration, archive)
                tests.append((archive, p.submit(binding)))

            finished_tests_count = 0
            failed_tests: list[tuple[str, BaseException]] = []
            while finished_tests_count < len(tests):
                for test in tests:
                    if not test[1].done():
                        continue
                    finished_tests_count += 1
                    err = test[1].exception()
                    if err != None:
                        failed_tests.append((os.path.basename(test[0]), err))

            if len(failed_tests) > 0:
                logger.critical("There are failed tests in test_integration.")
                for failed_test in failed_tests:
                    logger.critical(f"{failed_test[0]}: {failed_test[1]}")
