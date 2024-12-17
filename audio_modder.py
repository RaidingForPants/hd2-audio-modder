import os
import subprocess
import shutil

import config as cfg 
import db

from tkinter.messagebox import showwarning
from tkinter.messagebox import showerror

from const_global import GAME_FILE_LOCATION, language_lookup
from const_global import CACHE, DEFAULT_WWISE_PROJECT, SYSTEM, VGMSTREAM, \
        WWISE_CLI
from log import logger
from ui_main_window import MainWindow
from ui_controller_file import FileHandler
from ui_controller_sound import SoundHandler
    

if __name__ == "__main__":
    app_state: cfg.Config | None = cfg.load_config()
    if app_state == None:
        exit(1)

    os.environ["GAME_FILE_LOCATION"] = app_state.game_data_path

    try:
        if not os.path.exists(CACHE):
            os.mkdir(CACHE, mode=0o777)
    except Exception as e:
        showerror("Error when initiating application", 
                    "Failed to create application caching space")
        exit(1)

    if not os.path.exists(VGMSTREAM):
        logger.error("Cannot find vgmstream distribution! "
                     f"Ensure the {os.path.dirname(VGMSTREAM)} folder is "
                     "in the same folder as the executable")
        showwarning(title="Missing Plugin", 
                    message="Cannot find vgmstream distribution! Audio playback "
                    "is disabled.")
                     
    if not os.path.exists(WWISE_CLI) and SYSTEM != "Linux":
        logger.warning("Wwise installation not found. WAV file import is disabled.")
        showwarning(title="Missing Plugin", 
                    message="Wwise installation not found. WAV file import is "
                    "disabled.")
    
    if os.path.exists(WWISE_CLI) and not os.path.exists(DEFAULT_WWISE_PROJECT):
        process = subprocess.run([
            WWISE_CLI,
            "create-new-project",
            DEFAULT_WWISE_PROJECT,
            "--platform",
            "Windows",
            "--quiet",
        ])
        if process.returncode != 0:
            logger.error("Error creating Wwise project. Audio import restricted "
                         "to .wem files only")
            showwarning(title="Wwise Error", 
                        message="Error creating Wwise project. Audio import "
                        "restricted to .wem files only")
            WWISE_CLI = ""

    lookup_store: db.LookupStore | None = None
    
    if not os.path.exists(GAME_FILE_LOCATION()):
        showwarning(title="Missing Game Data", 
                    message="No folder selected for Helldivers data folder. "
                    "Audio archive search is disabled.")
    elif os.path.exists("hd_audio_db.db"):
        sqlite_initializer = db.config_sqlite_conn("hd_audio_db.db")
        try:
            lookup_store = db.SQLiteLookupStore(sqlite_initializer, logger)
        except Exception as err:
            logger.error("Failed to connect to audio archive database", 
                         stack_info=True)
            lookup_store = None
    else:
        logger.warning("Please ensure `hd_audio_db.db` is in the same folder as "
                "the executable to enable built-in audio archive search.")
        logger.warning("Built-in audio archive search is disabled. "
                "Please refer to the information in Google spreadsheet.")
        showwarning(title="Missing Plugin",
                    message="Audio database not found. Audio archive search is "
                    "disabled.")
        
    language = language_lookup("English (US)")
    sound_handler = SoundHandler()
    file_handler = FileHandler()
    window = MainWindow(app_state, lookup_store, file_handler, sound_handler)
    
    app_state.save_config()

    if os.path.exists(CACHE):
        shutil.rmtree(CACHE)
