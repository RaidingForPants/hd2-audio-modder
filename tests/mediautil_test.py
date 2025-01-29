import os
import shutil
import unittest

from env import TMP
from mediautil import to_wave_batch


class TestMediaUtil(unittest.IsolatedAsyncioTestCase):

    async def test_to_wave_batch(self):
        os.mkdir(TMP)

        mp3_files: list[str] = [entry.path for entry in os.scandir("tests/mockup/audio_files/mp3")]
        ogg_files: list[str] = [entry.path for entry in os.scandir("tests/mockup/audio_files/ogg")]
        print(f"input_mp3_files: {mp3_files}")
        print(f"input_mp3_files: {ogg_files}")
        results = await to_wave_batch(mp3_files)
        for result in results:
            print(result[0])
            self.assertEqual(result[1], 0)
        results = await to_wave_batch(ogg_files)
        for result in results:
            print(result[0])
            self.assertEqual(result[1], 0)

        shutil.rmtree(TMP)
