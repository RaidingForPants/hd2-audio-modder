import os
import pickle
import tkinter.messagebox as message_box
import tkinter.filedialog as file_dialog
import pathlib

from log import logger

class Config:

    def __init__(self,
                 game_data_path: str,
                 recent_files: list[str] = [],
                 theme: str = "dark_mode",
                 ui_scale: float = 1.0,
                 rowheight_scale: float = 1.0,
                 rad_tools_path: str = "",
                 wwise_path: str = "",
                 workspace_paths: set[str] = set()):
        self.game_data_path = game_data_path
        self.rad_tools_path = rad_tools_path
        self.wwise_path = wwise_path
        self.recent_files = recent_files
        self.theme = theme
        self.ui_scale = ui_scale
        self.rowheight_scale = rowheight_scale
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

    def get(self, attr: str, default=None):
        return getattr(self, attr, default)

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
        cfg.theme = cfg.get("theme", "dark_mode")
        cfg.ui_scale = cfg.get("ui_scale", 1.0)
        cfg.rad_tools_path = cfg.get("rad_tools_path", "")
        cfg.wwise_path = cfg.get("wwise_path", "")
        cfg.rowheight_scale = cfg.get("rowheight_scale", 1.0)
        cfg.recent_files = cfg.get("recent_files", [])
        cfg.recent_files = [file for file in cfg.recent_files if os.path.exists(file)]
        cfg.save_config()
        return cfg

    game_data_path: str | None = _select_game_data_path()
    if game_data_path is None:
        return None
    new_cfg: Config = Config(game_data_path)
    new_cfg.save_config(config_path)

    return new_cfg

def _select_game_data_path() -> str | None:
    while True:
        game_data_path: str = file_dialog.askdirectory(
            mustexist=True,
            title="Locate game data directory for Helldivers 2"
        )
        if os.path.exists(game_data_path):
            path = pathlib.Path(game_data_path)
            if path.match("*/steamapps/common/Helldivers 2/data"):
                return game_data_path
            elif path.match("*/steamapps/common/Helldivers 2/*") or path.match("*/steamapps/common/Helldivers 2/*/*"):
                for parent_path in path.parents:
                    if parent_path.match("*/steamapps/common/Helldivers 2") and os.path.exists(os.path.join(str(parent_path), "data")):
                        return os.path.join(str(parent_path), "data")
            elif path.match("*/steamapps/common/Helldivers 2"):
                if os.path.exists(os.path.join(str(path), "data")):
                    return os.path.join(str(path), "data")
            elif path.match("*/steamapps/common"):
                if os.path.exists(os.path.join(str(path), "data")):
                    return os.path.join(str(path), "data")
            elif path.match("*/steamapps"):
                if os.path.exists(os.path.join(str(path), "common", "Helldivers 2", "data")):
                    return os.path.join(str(path), "common", "Helldivers 2", "data")
        if not game_data_path:
            return ""
        response = message_box.askyesnocancel(title="Unexpected folder location", message=f"{game_data_path} does not appear to be the default install location for Helldivers 2. Would you like to use this as your game data folder?")
        if response == None or response == ():
            return ""
        if response:
            return game_data_path
        if not response:
            pass
