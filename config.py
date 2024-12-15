import os
import pickle
import tkinter.messagebox as message_box
import tkinter.filedialog as file_dialog
import uuid

from log import logger


class Separator:

    def __init__(self, uid: str, label: str, parent_entry_id: str, entry_ids: list[str]):
        self.uid = uid
        self.label = label
        self.parent_entry_id = parent_entry_id
        self.entry_ids = entry_ids

    def __str__(self):
        return "\n".join([self.uid, self.label, self.parent_entry_id, *self.entry_ids])

"""
Data class to encapsulate relationship of separators across archives and 
different tree entry.

TBH, this relationship is good enough to be mapped in a database.
"""
class SeparatorDB:

    """
    archive_mapping: name space for separator 
        - dictionary[archive_path, set[separator_uuid]]
    parent_mapping: helper data when laying down separator during tree view entry
    creation.
        - dictionary[entry_id, set[separator_uuid]]
    """
    def __init__(self, 
                 separators: dict[str, Separator] = {},
                 separator_children: dict[str, str] = {},
                 archive_namespace: dict[str, set[str]] = {}, 
                 separator_parents: dict[str, set[str]] = {}):
        self.separators = separators
        self.separator_children = separator_children
        self.archive_namespace = archive_namespace
        self.separator_parents = separator_parents


class Config:

    def __init__(self,
                 game_data_path: str,
                 separators_db: SeparatorDB,
                 recent_files: list[str] = [],
                 theme: str = "dark_mode",
                 workspace_paths: set[str] = set()):
        self.game_data_path = game_data_path
        self.separators_db = separators_db
        self.recent_files = recent_files
        self.theme = theme
        self.workspace_paths = workspace_paths

    """
    @return (int): A status code to tell whether there are new workspace being 
    added
    """
    def add_new_workspace(self, workspace_path : str = "") -> int:
        if not os.path.exists(workspace_path):
            return 1
        if workspace_path in self.workspace_paths:
            return 1
        self.workspace_paths.add(workspace_path)
        return 0 

    def add_separator(self, 
                      label: str, 
                      archive_path: str, 
                      parent_id: str, 
                      entries: list[str]):
        uid = uuid.uuid4().hex

        if uid in self.separators_db.separators:
            logger.error("Hash collision when creating a new separator!")
            return ""

        if archive_path not in self.separators_db.archive_namespace:
            self.separators_db.archive_namespace[archive_path] = set()

        if uid in self.separators_db.archive_namespace[archive_path]:
            logger.error("Hash collision when creating a new separator!"
                         " Collision in archive namespace")

        if parent_id not in self.separators_db.separator_parents:
            self.separators_db.separator_parents[parent_id] = set()

        if uid in self.separators_db.separator_parents[parent_id]:
            logger.error("Hash collision when creating a new separator!"
                         " Collision in parent scope")
        separator = Separator(uid, label, parent_id, entries)

        self.separators_db.separators[uid] = separator
        self.separators_db.archive_namespace[archive_path].add(uid)
        self.separators_db.separator_parents[parent_id].add(uid)

        return uid

    def rename_separator(self, uid: str, label: str):
        if uid in self.separators_db.separators:
            self.separators_db.separators[uid].label = label

    def remove_separator(self, uid: str):
        if uid in self.separators_db.separators:
            self.separators_db.separators.pop(uid)
        for _, v in self.separators_db.archive_namespace.items():
            if uid in v:
                v.remove(uid)
        for _, v in self.separators_db.separator_parents.items():
            if uid in v:
                v.remove(uid)

    def save_config(self, config_path: str = "config.pickle"):
        try:
            with open(config_path, "wb") as f:
                pickle.dump(self, f)
        except Exception as e:
            logger.error("Error occur when serializing configuration")
            logger.error(e)

    def get_workspace_paths(self) -> set[str]:
        # Validate and update all workspace paths to ensure they exists
        self.workspace_paths = set([p for p in self.workspace_paths 
                                    if os.path.exists(p)])
        return self.workspace_paths

def load_config(config_path: str = "config.pickle") -> Config | None:
    if os.path.exists(config_path):
        cfg: Config | None = None
        try:
            # Reading existence configuration
            with open(config_path, "rb") as f:
                cfg = pickle.load(f)
            if not isinstance(cfg, Config):
                raise ValueError("Invalid configuration data")
        except Exception as e:
            logger.critical("Error occurred when de-serializing configuration")
            logger.critical(e)
            logger.critical(f"Delete {config_path} to resolve the error")
            cfg = None

        if cfg == None:
            return None

        if not os.path.exists(cfg.game_data_path):
            # Old game data path is no longer valid, require update
            game_data_path: str | None = _select_game_data_path()
            if game_data_path is None:
                return None
            cfg.game_data_path = game_data_path
            cfg.workspace_paths = set([p for p in cfg.workspace_paths 
                                   if os.path.exists(p)])

        # For backwards compatibility with configuration created before these 
        # were added
        if not hasattr(cfg, "theme"):
            cfg.theme = "dark_mode"
        if not hasattr(cfg, "recent_files"):
            cfg.recent_files = []
        if not hasattr(cfg, "separators_db"):
            cfg.separators_db = SeparatorDB()

        cfg.recent_files = [file for file in cfg.recent_files 
                                 if os.path.exists(file)]
        cfg.save_config()

        return cfg

    game_data_path: str | None = _select_game_data_path()
    if game_data_path is None:
        return None
    new_cfg: Config = Config(game_data_path, SeparatorDB())
    new_cfg.save_config(config_path)

    return new_cfg

def _select_game_data_path() -> str | None:
    while True:
        game_data_path: str = file_dialog.askdirectory(
            mustexist=True,
            title="Locate game data directory for Helldivers 2"
        ).lower()

        exists = os.path.exists(game_data_path)
        is_data_folder = game_data_path.endswith("steamapps/common/helldivers 2/data")

        if exists and is_data_folder:
            return game_data_path

        res = message_box.askretrycancel(
                title="Invalid Folder", 
                message="Failed to locate valid Helldivers 2 install in this "
                        "folder.")
        if not res:
            return ""
