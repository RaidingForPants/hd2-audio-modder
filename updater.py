import requests
import zipfile
import sys
import time
import tkinter
import platform
import subprocess

download_url = sys.argv[1]
pid = sys.argv[2]

root = tkinter.Tk()
root.geometry("300x200")
frame = tkinter.Frame(root)
label = tkinter.Label(frame, "Waiting for audio modder to close...")

label.pack()
frame.pack()

root.mainloop()

time.sleep(2)

if platform.system() in ["Darwin", "Linux"]:
    filename = "audio_modder"
elif platform.system() == "Windows":
    filename = "audio_modder.exe"
zipfilename = download_url.split("/")[-1]

if update_available:
    r = requests.get(download_url)
    if r.status_code != 200:
        tkinter.filedialog.showwarning(title="Error", message="Error fetching update")
    else:
        with open(zipfilename, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        z = zipfile.Zipfile(zipfilename)
        with z.open(filename) as f:
            with open(filename) as f2:
                f2.write(f.read())
        os.remove(z)
        tkinter.filedialog.showinfo(title="Success", message="The audio modding tool has been updated")
                
subprocess.run(
    [
        filename
    ],
    creationflags=subprocess.DETACHED_PROCESS
)