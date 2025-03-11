import requests
import zipfile
import sys
import time
import tkinter
import platform
import subprocess
from tkinter.messagebox import showwarning
from tkinter.messagebox import showinfo

download_url = sys.argv[1]
pid = sys.argv[2]


if platform.system() in ["Darwin", "Linux"]:
    filename = "audio_modder"
elif platform.system() == "Windows":
    filename = "audio_modder.exe"
zipfilename = download_url.split("/")[-1]

try:

    r = requests.get(download_url)
    if r.status_code != 200:
        showwarning(title="Error", message="Error fetching update")
    else:
        with open(zipfilename, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        z = zipfile.ZipFile(zipfilename)
        with z.open(filename, "r") as f:
            with open(filename, "wb") as f2:
                f2.write(f.read())
        z.close()
        os.remove(zipfilename)
        showinfo(title="Success", message="The audio modding tool has been updated and will now restart.")
                    
except Exception as e:
    print(e)

subprocess.Popen(
    [
        filename
    ],
    creationflags=subprocess.DETACHED_PROCESS
)
