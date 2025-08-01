import os
import pathlib
import platform
import posixpath
import sys

import fileutil

from log import logger


DIR = fileutil.to_posix(os.path.dirname(__file__))
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    DIR = fileutil.to_posix(os.path.dirname(sys.argv[0]))

CACHE = posixpath.join(DIR, ".cache")
TMP = posixpath.join(DIR, ".tmp")

DIR = os.path.abspath(DIR)
CACHE = os.path.abspath(CACHE)
TMP = os.path.abspath(TMP)

DEFAULT_WWISE_PROJECT = posixpath.join(
    DIR, "AudioConversionTemplate/AudioConversionTemplate.wproj")

SYSTEM = platform.system()

FFMPEG = ""
VGMSTREAM = ""
SYS_CLIPBOARD = ""
WWISE_CLI = ""
WWISE_VERSION = ""
RAD_TOOLS = ""
RAD_COMPRESS = "binkc"
RAD_CONVERT = "binkconv"
RAD_PLAY = ""

match SYSTEM:
    case "Windows":
        FFMPEG = "ffmpeg.exe"
        RAD_TOOLS = "radvideo64.exe"
        RAD_PLAY = "binkplay.exe"
        VGMSTREAM = "vgmstream-win64/vgmstream-cli.exe"
        if "WWISEROOT" in os.environ:
            WWISE_CLI = posixpath.join(
                    fileutil.to_posix(os.environ["WWISEROOT"]),
                    "Authoring/x64/Release/bin/WwiseConsole.exe"
            )
        else:
            logger.warning("Failed to locate WwiseConsole.exe")
        SYS_CLIPBOARD = "clip"
    case "Linux":
        VGMSTREAM = "vgmstream-linux/vgmstream-cli"
        FFMPEG = "ffmpeg"
        WWISE_CLI = ""
        logger.warning("Wwise integration is not supported for Linux. WAV file "
                       "import is disabled.")
        SYS_CLIPBOARD = "xclip"
    case "Darwin":
        VGMSTREAM = "vgmstream-macos/vgmstream-cli"
        FFMPEG = "ffmpeg"
        if os.path.exists("/Applications/Audiokinetic"):
            match = next(pathlib.Path("/Applications/Audiokinetic").glob("Wwise*"))
            WWISE_CLI = os.path.join(match, 
                                     "Wwise.app/Contents/Tools/WwiseConsole.sh")
        SYS_CLIPBOARD = "pbcopy"

if not os.path.exists(WWISE_CLI):
    WWISE_CLI = ""


def get_data_path():
    """
    @return
    - Return absolute path POSIX
    """
    location = os.environ.get("HD2DATA")
    return "" if location == None else location


def set_data_path(path: str):
    if path != "" or os.path.exists(path):
        os.environ["HD2DATA"] = fileutil.to_posix(path)
