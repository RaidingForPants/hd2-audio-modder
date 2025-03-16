import unittest

from backend.db import SQLiteDatabase, config_sqlite_conn
from wwise_hierarchy import ak_media_id


class TestSourceIDGen(unittest.TestCase):

    def test_n_times(self):
        conn_config = config_sqlite_conn("database")
        db = SQLiteDatabase(conn_config)
        for _ in range(100):
            print(ak_media_id(db))
