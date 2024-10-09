import sqlite3

from logging import Logger
from typing import Callable

from log import logger

def config_sqlite_conn(db_path: str):
    conn: sqlite3.Connection | None = None

    def _get_sqlite_conn() -> sqlite3.Connection | None:
        nonlocal conn
        if conn != None:
            return conn
        try:
            conn = sqlite3.connect(db_path)
        except Exception as err:
            logger.error("Failed to connect helldiver audio source database")
            conn = None
        return conn

    return _get_sqlite_conn


"""
Database Access Interface
"""
class LookupStore:

    def query_helldiver_four_vo(self, query: str) -> dict[str, str]:
        return {} 

    def query_helldiver_audio_archive(self, category: str = "") -> dict[str, str]:
        return {}

    def query_helldiver_audio_archive_category(self) -> list[str]:
        return []


class SQLiteLookupStore (LookupStore):

    def __init__(self, initializer: Callable[[], sqlite3.Connection | None], 
                 logger: Logger):
        self.conn = initializer()
        if self.conn != None:
            self.cursor = self.conn.cursor()
        else:
            logger.warning("Builtin audio source lookup is disabled due to database connection error")
    
    def query_helldiver_audio_archive(self, category: str = "") -> dict[str, str]:
        rows: sqlite3.Cursor
        if category == "":
            rows = self.cursor.execute("SELECT archive_id, basename FROM helldiver_audio_archives")
        else:
            args = (category,)
            rows = self.cursor.execute("SELECT archive_id, basename FROM helldiver_audio_archives WHERE category = ?", args)
        return {row[0]: row[1] for row in rows}

    def query_helldiver_audio_archive_category(self) -> list[str]:
        rows = self.cursor.execute("SELECT DISTINCT category FROM helldiver_audio_archives")
        return [row[0] for row in rows]

    def query_helldiver_four_vo(self, query: str) -> dict[str, str]:
        if len(query) == "":
            return {}

        if self.cursor == None:
            return {}
        # TO-DO the possibilities of verify SQL injection
        args = (" OR ".join([f"\"{token}\"" for token in query.strip().split(" ") 
                             if len(token) > 0]), )
        rows = self.cursor.execute("SELECT file_id, transcription FROM helldiver_four_vo_fts WHERE transcription MATCH ? ORDER BY rank LIMIT 10", 
                                   args)
        return {row[0]: row[1] for row in rows} 
