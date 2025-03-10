import sqlite3
import uuid
import os

from logging import Logger
from typing import Callable

def config_sqlite_conn(db_path: str):
    conn: sqlite3.Connection | None = None

    def _get_sqlite_conn() -> sqlite3.Connection | None:
        nonlocal conn
        if conn != None:
            return conn
        conn = sqlite3.connect(db_path)
        return conn

    return _get_sqlite_conn
    
def get_db_version(db_path: str):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    result = cursor.execute("PRAGMA user_version")
    return result.fetchone()[0]

class HelldiverAudioArchiveName:

    def __init__(self,
                 audio_archive_name_id: str,
                 audio_archive_name: str):
        self.audio_archive_name_id = audio_archive_name_id
        self.audio_archive_name = audio_archive_name

class HelldiverAudioArchive:

    def __init__(self, 
                 audio_archive_id: str, 
                 audio_archive_name_id: str,
                 audio_archive_name: str):
        self.audio_archive_id = audio_archive_id
        self.audio_archive_name_id = audio_archive_name_id
        self.audio_archive_name = audio_archive_name

class HelldiverAudioSource:

    def __init__(self,
                 audio_source_id: int,
                 linked_audio_archive_ids: set[str],
                 linked_audio_archive_name_ids: set[str]
                 ):
        self.audio_source_id = audio_source_id
        self.linked_audio_archive_ids = linked_audio_archive_ids
        self.linked_audio_archive_name_ids = linked_audio_archive_name_ids
        
class CustomNameStore:
    
    def __init__(self, name_db_path: str = ""):
        if os.path.exists(name_db_path):
        self.conn = sqlite3.connect(name_db_path)
        if self.conn != None:
            self.cursor = self.conn.cursor()
            
    def add_soundbank_name(self, soundbank, friendlyname: str):
        self.cursor.execute("INSERT INTO soundbanks id, name, friendlyname, VALUES (?, ?, ?)", (soundbank.get_id(), soundbank.dep.data, friendlyname))
        self.conn.commit()
            
    def lookup_soundbank(self, key: str):
        key = str(key)
        try:
            t = int(key)
            is_bank_id = True
        except ValueError:
            is_bank_id = False
        if is_bank_id:
            results = self.cursor.execute("SELECT id, name, friendlyname, archive, language FROM soundbanks WHERE id=?", (key,))
        else:
            results = self.cursor.execute("SELECT id, name, friendlyname, archive, language FROM soundbanks WHERE name=?", (key,))
        result = results.fetchone()
        if result:
            return LookupResult(result[0], result[1], result[2], result[3], result[4])
        else:
            return LookupResult(key, key, key, key, key, success=False)
        
        
class LookupResult:
    
    def __init__(self,
                 id: str,
                 name: str,
                 friendlyname: str,
                 archive: str,
                 language: str,
                 success: bool = True
                 ):
        self.id = id
        self.name = name
        self.friendlyname = friendlyname
        self.archive = archive
        self.language = language
        self.success = success
        
class FriendlyNameLookup:
    
    def __init__(self, name_db_path: str = ""):
        self.conn = sqlite3.connect(name_db_path)
        if self.conn != None:
            self.cursor = self.conn.cursor()
        self.custom_name_store = None
            
    def set_custom_name_store(self, custom_name_store):
        self.custom_name_store = custom_name_store
            
    def lookup_soundbank(self, key: str):
        if self.custom_name_store:
            result = self.custom_name_store.lookup_soundbank(key)
            if result.success:
                return result
            
        key = str(key)
        try:
            t = int(key)
            is_bank_id = True
        except ValueError:
            is_bank_id = False
        if is_bank_id:
            results = self.cursor.execute("SELECT id, name, friendlyname, archive, language FROM soundbanks WHERE id=?", (key,))
        else:
            results = self.cursor.execute("SELECT id, name, friendlyname, archive, language FROM soundbanks WHERE name=?", (key,))
        result = results.fetchone()
        if result:
            return LookupResult(result[0], result[1], result[2], result[3], result[4])
        else:
            return LookupResult(key, key, key, key, key, success=False)
            
    def lookup_hierarchy_entry(self, entry_id):
        
        entry_id = str(entry_id)
        
        if self.custom_name_store:
            pass
            
        results = self.cursor.execute("SELECT id, friendlyname FROM hierarchy_entries WHERE id=?", (entry_id,))
        result = results.fetchone()
        if result:
            return LookupResult(result[0], "", result[1], "", "", "")
        else:
            return LookupResult("", "", "", "", "", success=False)
            
    def lookup_audio_source(self, source_id):
        
        source_id = str(source_id)
        
        if self.custom_name_store:
            pass
            
        results = self.cursor.execute("SELECT id, resource_id, friendlyname FROM audio_sources WHERE id=? OR resource_id=?", (source_id, source_id))
        result = results.fetchone()
        if result:
            return LookupResult(result[0], "", result[1], "", "", "")
        else:
            return LookupResult("", "", "", "", "", success=False)
            
            
            
    def query_soundbanks(self, language=""):
        r = []
        if language == "":
            results = self.cursor.execute("SELECT id, name, friendlyname, archive, language FROM soundbanks")
        else:
            results = self.cursor.execute("SELECT id, name, friendlyname, archive, language FROM soundbanks WHERE language IN (?, ?)", (language, "none"))
        for result in results.fetchall():
            r.append(LookupResult(result[0], result[1], result[2], result[3], result[4]))
        return r

"""
Database Access Interface
"""
class LookupStore:

    def query_helldiver_four_vo(self, query: str) -> dict[str, str]:
        return {} 

    def query_helldiver_audio_archive(self, category: str = "") -> \
            list[HelldiverAudioArchive]:
        return []

    def query_helldiver_audio_archive_category(self) -> list[str]:
        return []

    def write_helldiver_audio_source_bulk(self,
                                          sources: list[HelldiverAudioSource]):
        pass

class SQLiteLookupStore (LookupStore):

    def __init__(self, initializer: Callable[[], sqlite3.Connection | None], 
                 logger: Logger):
        self.conn = initializer()
        self.logger = logger
        if self.conn != None:
            self.cursor = self.conn.cursor()
        else:
            logger.warning("Builtin audio source lookup is disabled due to \
                    database connection error")
    
    def query_helldiver_audio_archive(self, category: str = "") -> \
            list[HelldiverAudioArchive]:
        rows: sqlite3.Cursor
        archives: list[HelldiverAudioArchive] = []
        try:
            if category == "":
                rows = self.cursor.execute("SELECT \
                        id, \
                        name, \
                        friendlyname, \
                        archive, \
                        language, \
                        FROM soundbanks")
            else:
                args = (category,)
                rows = self.cursor.execute("SELECT \
                        audio_archive_id, \
                        helldiver_audio_archive.audio_archive_name_id, \
                        audio_archive_name \
                        FROM helldiver_audio_archive INNER JOIN \
                        helldiver_audio_archive_name ON \
                        helldiver_audio_archive.audio_archive_name_id = \
                        helldiver_audio_archive_name.audio_archive_name_id \
                        WHERE audio_archive_category = ?", args)
            archives = [HelldiverAudioArchive(row[0], row[1], row[2]) 
                        for row in rows]
        except (sqlite3.OperationalError, sqlite3.IntegrityError) as err:
            self.logger.critical(err, stack_info=True)
        finally:
            return archives 

    def query_helldiver_audio_archive_category(self) -> list[str]:
        audio_archive_categories: list[str] = []
        try:
            rows = self.cursor.execute("SELECT DISTINCT audio_archive_category \
                    FROM helldiver_audio_archive")
            audio_archive_categories = [row[0] for row in rows]
        except (sqlite3.OperationalError, sqlite3.IntegrityError) as err:
            self.logger.critical(err, stack_info=True)
        finally:
            return audio_archive_categories

#    def query_helldiver_four_vo(self, query: str) -> dict[str, str]:
#        if len(query) == "":
#            return {}
#
#        if self.cursor == None:
#            return {}
#        # TO-DO the possibilities of verify SQL injection
#        args = (" OR ".join([f"\"{token}\"" for token in query.strip().split(" ") 
#                             if len(token) > 0]), )
#        rows = self.cursor.execute("", args)
#        return {row[0]: row[1] for row in rows} 

    def write_helldiver_audio_source_bulk(self,
                                          sources: list[HelldiverAudioSource]):
        if self.conn == None or self.cursor == None:
            return
        try:
            self.cursor.execute("DELETE FROM helldiver_audio_source")
            self.conn.commit()
            data = [
                    (
                        uuid.uuid4().hex,
                        str(source.audio_source_id),
                        ",".join(source.linked_audio_archive_ids),
                        ",".join(source.linked_audio_archive_name_ids)
                    )
                    for source in sources
                    ]
            self.cursor.executemany("INSERT INTO helldiver_audio_source (\
                    audio_source_db_id, \
                    audio_source_id, \
                    linked_audio_archive_ids, \
                    linked_audio_archive_name_ids) VALUES (\
                    ?, ?, ?, ?)", data)
            self.conn.commit()
        except (sqlite3.OperationalError, sqlite3.IntegrityError) as err:
            self.logger.error(err)
