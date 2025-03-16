import os
import posixpath as xpath
import unittest

import env

from core import GameArchive
from log import logger
from tests.parser_test_common import test_all_archive_sync


class TestParserIntegration(unittest.TestCase):

    def _test_build(self, file: str):
        archive = GameArchive.from_file(file)
        archive.to_file("I:/parser_test_built")

    def test_build(self):
        logger.critical("Running test_build...")
        test_all_archive_sync(
            self._test_build,
            [
                "2e24ba9dd702da5c",
                "fdf011daecf24312",
                "3b2c86dd5b316eb2",
                "89de9c3d26d2adc1",
                "046d4441a6dae0a9",
                "3b2c86dd5b316eb2",
            ]
        )

        logger.critical("Verifying built archives and generating imported archives...")
        files = os.scandir("I:/parser_test_built")
        for file in files:
            if not file.is_file():
                continue

            archive, ext = os.path.splitext(file.path)

            basename = os.path.basename(archive)

            if ext != ".stream":
                continue

            built_archive = GameArchive.from_file(archive)
            original_archive = GameArchive.from_file(xpath.join(env.get_data_path(), basename))

            original_banks = original_archive.get_wwise_banks()
            built_banks = built_archive.get_wwise_banks()
            for key, bank in built_banks.items():
                self.assertIn(key, original_banks)
                self.assertIsNotNone(bank.hierarchy)
                original_banks[key].import_hierarchy(bank.hierarchy)
            original_archive.to_file("I:/parser_test_imported")

        logger.critical("Verified imported archives...")
        files = os.scandir("I:/parser_test_imported")
        for file in files:
            if not file.is_file():
                continue

            archive, ext = os.path.splitext(file.path)

            basename = os.path.basename(archive)

            if ext != ".stream":
                continue

            GameArchive.from_file(archive)
        logger.critical("Done")
