import os
import sqlite3

from typing import Callable


def config_sqlite_conn(db_path: str):
    """
    @exception
    - OSError
    """
    if not os.path.exists(db_path):
        raise OSError(f"Database {db_path} does not exists.")

    def _get_sqlite_conn() -> sqlite3.Connection | None:
        """
        @exception
        - sqlite3.Error
        """
        conn = sqlite3.connect(db_path, timeout = 5.0)
        return conn

    return _get_sqlite_conn


class SQLiteDatabase:
    
    def __init__(
        self,
        initializer: Callable[[], sqlite3.Connection | None]
    ) -> None:
        self.conn = initializer()
        if self.conn != None:
            self.cursor = self.conn.cursor()
        else:
            raise RuntimeError("Failed to establish database connection")

    def close(self, commit = False):
        """
        @exception
        - Any
        """
        if self.conn != None:
            self.cursor.close()
            if commit: 
                self.conn.commit()
            self.conn.close()

    def commit(self):
        if self.conn != None:
            self.conn.commit()

    def has_audio_source_id(self, source_id: int):
        query = "SELECT COUNT(*) FROM sound WHERE wwise_short_id = ?"
        res = self.cursor.execute(query, (source_id, )).fetchone()
        return res[0] > 0
