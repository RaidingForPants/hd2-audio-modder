import os
import pickle
import tkinter.messagebox as message_box
import tkinter.filedialog as file_dialog

from log import logger

class Config:

    def __init__(self,
                 game_data_path: str,
                 wwise_cli_path: str,
                 project_path: str = "",
                 recent_files: list[str] = [],
                 theme: str = "dark_mode",
                 workspace_paths: set[str] = set()):
        self.game_data_path = game_data_path
        self.project_path = project_path
        self.recent_files = recent_files
        self.theme = theme
        self.workspace_paths = workspace_paths
        self.wwise_cli_path = wwise_cli_path

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
        abort = False
        try:
            if not os.path.exists(cfg.wwise_cli_path):
                wwise_cli_path: str | None = _select_wwise_cli_path()
                if wwise_cli_path is None:
                    abort = True
                    return
        except:
            wwise_cli_path = _select_wwise_cli_path()
            if wwise_cli_path is None:
                abort = True
        if abort:
            return None

        try: 
            _ = cfg.theme
        except:
            cfg.theme = "dark_mode"
        try:
            _ = cfg.recent_files
        except:
            cfg.recent_files = []
        cfg.save_config()
        return cfg

    game_data_path: str | None = _select_game_data_path()
    wwise_cli_path: str | None = _select_wwise_cli_path()
    if game_data_path is None:
        return None
    if wwise_cli_path is None:
        return None
    new_cfg: Config = Config(wwise_cli_path, game_data_path)
    new_cfg.save_config(config_path)

    return new_cfg

def _select_game_data_path() -> str | None:
    while True:
        game_data_path: str = file_dialog.askdirectory(
            mustexist=True,
            title="Locate game data directory for Helldivers 2"
        )
        if os.path.exists(game_data_path) \
                and game_data_path.endswith("steamapps/common/Helldivers 2/data"):
            return game_data_path
        res = message_box.askretrycancel(message="Invalid game data directory")
        if not res:
            return None

def _select_wwise_cli_path() -> str | None:
    while True:
        wwise_cli_path: str = file_dialog.askdirectory(mustexist=True,
                                                       title="Locate "
                                                       "WwiseConsole.exe")
        if os.path.exists(wwise_cli_path) \
                and wwise_cli_path.endswith("WwiseConsole.exe"):
            return wwise_cli_path
        res = message_box.askretrycancel(message="Invalid path for WwiseConsole")
        if not res:
            return None
