import os
import unittest

import env

from core import GameArchive
from wwise_hierarchy import RandomSequenceContainer, pack_cntr


class TestCntrParser(unittest.TestCase):

    def test_read_robust(self):
        os.environ["TEST"] = "1"
        files = os.scandir(env.get_data_path())

        for file in files:
            if not file.is_file():
                continue
            name, ext = os.path.splitext(file.path)
            if ext != ".stream":
                continue
            GameArchive.from_file(name)

    def test_robust(self):
        files = os.scandir(env.get_data_path())

        for file in files:
            if not file.is_file():
                continue
            name, ext = os.path.splitext(file.path)
            if ext != ".stream":
                continue

            ctrl_group = GameArchive.from_file(name)

            os.environ["TEST"] = "1"
            exp_group = GameArchive.from_file(name)

            os.environ["TEST"] = "0"

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
                self.assertTrue(exp_cntr_id in ctrl_cntrs)
                self.assertEqual(pack_cntr(exp_cntr), ctrl_cntrs[exp_cntr_id].get_data())
