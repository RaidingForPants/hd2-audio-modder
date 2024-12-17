import os
import pathlib
import platform
import sys

from tkinter.messagebox import showwarning

# [static const]
DEFAULT_CONVERSION_SETTING = "Vorbis Quality High"

MUSIC_TRACK = 11
SOUND = 2
BANK = 0
PREFETCH_STREAM = 1
STREAM = 2

VORBIS = 0x00040001

WWISE_BANK = 6006249203084351385
WWISE_DEP = 12624162998411505776
WWISE_STREAM = 5785811756662211598
STRING = 979299457696010195

LANGUAGE_MAPPING = ({
    "English (US)" : 0x03f97b57,
    "English (UK)" : 0x6f4515cb,
    "Français" : 4271961631,
    "Português 1": 1861586415,
    "Português 2": 1244441033,
    "Polski": 260593578,
    "日本語": 2427891497,
    "中文（繁體）": 2663028010,
    "中文（简体）": 2189905090,
    "Nederlands": 291057413,
    "한국어": 3151476177,
    "Español 1": 830498882,
    "Español 2": 3854981686,
    "Deutsch": 3124347884,
    "Italiano": 3808107213,
    "Русский": 3317373165
})
# [END]

# [platform based constant - set programmically]
DIR = os.path.dirname(__file__)
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    DIR = os.path.dirname(sys.argv[0])

CACHE = os.path.join(DIR, ".cache")

DEFAULT_WWISE_PROJECT = os.path.join(
        DIR, "AudioConversionTemplate/AudioConversionTemplate.wproj") 

FFMPEG = ""
SYSTEM = platform.system()
VGMSTREAM = ""
WWISE_CLI = ""
WWISE_VERSION = ""
match (SYSTEM):
    case "Windows":
        FFMPEG = "ffmpeg.exe"
        VGMSTREAM = "vgmstream-win64/vgmstream-cli.exe"
        if os.environ.get("WWISEROOT") != None:
            WWISE_CLI = os.path.join(os.environ["WWISEROOT"],
                                 "Authoring\\x64\\Release\\bin\\WwiseConsole.exe")
    case "Linux":
        FFMPEG = "ffmpeg"
        VGMSTREAM = "vgmstream-linux/vgmstream-cli"
        WWISE_CLI = ""
        showwarning(title="Unsupported", message="Wwise integration is not "
                    "supported for Linux. WAV file import is disabled")
    case "Darwin":
        FFMPEG = "ffmpeg"
        VGMSTREAM = "vgmstream-macos/vgmstream-cli"
        p = next(pathlib.Path("/Applications/Audiokinetic").glob("Wwise*"))
        WWISE_CLI = os.path.join(p, "Wwise.app/Contents/Tools/WwiseConsole.sh")

if os.path.exists(WWISE_CLI):
    if "Wwise2024" in WWISE_CLI:
        WWISE_VERSION = "2024"
    elif "Wwise2023" in WWISE_CLI:
        WWISE_VERSION = "2023"
else:
    WWISE_VERSION = ""


def GAME_FILE_LOCATION():
    p = os.environ.get("GAME_FILE_LOCATION")
    return p if p != None else ""
# [END]


# [global variables]
language = 0
num_segments = 0
# [END]


def language_lookup(lang_string):
    try:
        return LANGUAGE_MAPPING[lang_string]
    except:
        return int(lang_string)
