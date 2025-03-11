import os
import unittest

from core import GameArchive
from log import logger
from tests.parser_test_common import test_all_archive_sync


class TestParserIntegration(unittest.TestCase):

    def _test_build(self, file: str):
        archive = GameArchive.from_file(file)
        archive.to_file("I:/parser_test")

    def test_build(self):
        logger.critical("Running test_build...")
        test_all_archive_sync(self._test_build)

        logger.critical("Verifying build...")
        files = os.scandir("I:/parser_test")

        for file in files:
            if not file.is_file():
                continue

            archive, ext = os.path.splitext(file.path)

            if ext != ".stream":
                continue

            GameArchive.from_file(archive)
