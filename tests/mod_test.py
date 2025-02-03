import os
import posixpath as xpath
import unittest

from dataclasses import dataclass

import core

from fileutil import to_posix
from env import get_data_path, TMP
from log import logger


@dataclass
class MockUp:

    archive_name: str
    targets: dict[str, list[int]]


class TestMod(unittest.IsolatedAsyncioTestCase):

    async def test_import_wem_async(self):
        wem_dir = "tests/mockup/audio_files/wem"
 
        logger.info("Runing test_import_wem")
 
        test_cases = [
            MockUp(
                "2c26bc4c6592fa14",
                {
                    xpath.join(wem_dir, "GAU9_impact_close_01.wem"): [1004507351],
                    xpath.join(wem_dir, "GAU9_impact_close_02.wem"): [536635763],
                    xpath.join(wem_dir, "GAU9_impact_close_03.wem"): [413460094],
                    xpath.join(wem_dir, "GAU9_impact_close_04.wem"): [100470324]
                }
            )
        ]
 
        for test_case in test_cases:
            mod = core.Mod(test_case.archive_name)
            mod.load_archive_file(xpath.join(get_data_path(), test_case.archive_name))
 
            await mod.import_wems_async(test_case.targets)
 
            mod.write_patch(TMP, False)
 
        logger.info("Please open UI to verifiy the final result for `test_import_wem`")
 
    async def test_import_wav_async(self):
         wave_dir = to_posix(os.path.abspath("tests/mockup/audio_files/wave"))
 
         logger.info("Runing test_import_wav")
 
         test_cases = [
             MockUp(
                 "2c26bc4c6592fa14",
                 {
                     xpath.join(wave_dir, "GAU9_impact_close_01.WAV"): [1004507351],
                     xpath.join(wave_dir, "GAU9_impact_close_02.WAV"): [536635763],
                     xpath.join(wave_dir, "GAU9_impact_close_03.WAV"): [413460094],
                     xpath.join(wave_dir, "GAU9_impact_close_04.WAV"): [100470324]
                 }
             ),
             MockUp(
                 "a66d7cf238070ca7",
                 {
                     xpath.join(wave_dir, "akm_sandstorm/bolt_back_01.wav"): [224957304, 113945009, 510284008],
                     xpath.join(wave_dir, "akm_sandstorm/bolt_forward_01.wav"): [949543845, 540578400, 1004439290],
                     xpath.join(wave_dir, "akm_sandstorm/mag_in_01.wav"): [836761035, 41500478, 542512334],
                     xpath.join(wave_dir, "akm_sandstorm/mag_out_01.wav"): [558443132, 160331316, 943769138]
                 }
             ),
         ]
 
         for test_case in test_cases:
             mod = core.Mod("test_import_wave")
             mod.load_archive_file(xpath.join(get_data_path(), test_case.archive_name))
 
             await mod.import_wavs_async(test_case.targets)
 
             mod.write_patch(TMP, overwrite = False)
 
         logger.info("Please open UI to verifiy the final result for `test_import_wav`")

    async def test_import_files_async(self):
        wave_dir = to_posix(os.path.abspath("tests/mockup/audio_files/wave"))
        wem_dir = to_posix(os.path.abspath("tests/mockup/audio_files/wem"))
        ogg_dir = to_posix(os.path.abspath("tests/mockup/audio_files/ogg"))
        logger.info("Runing test_import_files_async")

        mod = core.Mod("test_import_files_async")
        mod.load_archive_file(xpath.join(get_data_path(), "2c26bc4c6592fa14"))
        mod.load_archive_file(xpath.join(get_data_path(), "a66d7cf238070ca7"))

        targets: dict[str, list[int]] = {
            xpath.join(wem_dir, "GAU9_impact_close_01.wem"): [1004507351],
            xpath.join(wem_dir, "GAU9_impact_close_02.wem"): [536635763],
            xpath.join(wem_dir, "GAU9_impact_close_03.wem"): [413460094],
            xpath.join(wem_dir, "GAU9_impact_close_04.wem"): [100470324],
            xpath.join(wave_dir, "akm_sandstorm/bolt_back_01.wav"): [224957304, 113945009, 510284008],
            xpath.join(wave_dir, "akm_sandstorm/bolt_forward_01.wav"): [949543845, 540578400, 1004439290],
            xpath.join(wave_dir, "akm_sandstorm/mag_in_01.wav"): [836761035, 41500478, 542512334],
            xpath.join(wave_dir, "akm_sandstorm/mag_out_01.wav"): [558443132, 160331316, 943769138],
            xpath.join(ogg_dir, "m1garand_core_single_01.ogg"): [101340640],
            xpath.join(ogg_dir, "m1garand_core_single_02.ogg"): [947154282],
            xpath.join(ogg_dir, "m1garand_core_single_03.ogg"): [872092613],
            xpath.join(ogg_dir, "m1garand_core_single_04.ogg"): [81887028],
        }

        await mod.import_files_async(targets)

        mod.write_patch(TMP, overwrite = False)
        
        logger.info("Please open UI to verifiy the final result for `test_import_wav`")

    async def test_write_patch_async(self):
        wave_dir = to_posix(os.path.abspath("tests/mockup/audio_files/wave"))
 
        logger.info("Runing test_import_wav")
 
        test_cases = [
            MockUp(
                "2c26bc4c6592fa14",
                {
                    xpath.join(wave_dir, "GAU9_impact_close_01.WAV"): [1004507351],
                    xpath.join(wave_dir, "GAU9_impact_close_02.WAV"): [536635763],
                    xpath.join(wave_dir, "GAU9_impact_close_03.WAV"): [413460094],
                    xpath.join(wave_dir, "GAU9_impact_close_04.WAV"): [100470324]
                }
            ),
            MockUp(
                "a66d7cf238070ca7",
                {
                    xpath.join(wave_dir, "akm_sandstorm/bolt_back_01.wav"): [224957304, 113945009, 510284008],
                    xpath.join(wave_dir, "akm_sandstorm/bolt_forward_01.wav"): [949543845, 540578400, 1004439290],
                    xpath.join(wave_dir, "akm_sandstorm/mag_in_01.wav"): [836761035, 41500478, 542512334],
                    xpath.join(wave_dir, "akm_sandstorm/mag_out_01.wav"): [558443132, 160331316, 943769138]
                }
            ),
        ]
 
        for test_case in test_cases:
            mod = core.Mod("test_import_wave")
            mod.load_archive_file(xpath.join(get_data_path(), test_case.archive_name))
 
            await mod.import_wavs_async(test_case.targets)
            await mod.write_patch_async(TMP, overwrite = False)
 
        logger.info("Please open UI to verifiy the final result for `test_import_wav`")
