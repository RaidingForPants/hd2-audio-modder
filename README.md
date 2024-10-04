# Audio and Text Modder For Helldivers 2

I made this program to help make modding audio data easier.

[Mini tutorial for audio modding](https://docs.google.com/document/d/e/2PACX-1vT5mFXlk0iPGF-yoR3hMPrws3iPa4cY5O6PjzLcgz3Jj9vHUh5mYN1P1uWb6QiPA8K5rcvac929icV2/pub)

Thanks to everyone behind the [Helldivers 2 Blender Addon](https://github.com/Boxofbiscuits97/HD2SDK-CommunityEdition) for letting me use some of their code.

You can use the prebuilt executables (built with PyInstaller) in the releases tab, or you can run the Python.

If you run the Python code, you will need the appropriate distribution of [vgmstream](https://vgmstream.org/) to play audio from within the program. Place the vgmstream folder into the same folder as the Python code.

## Running the Python code

### Windows
Install [Python 3](https://www.python.org/downloads/windows/). Make sure to check in the Python installer the optional feature "tcl/tk and IDLE".

Install the dependencies:

```python -m pip install -r requirements.txt```

Run the program:

```python audio_modder.py```

### Linux
PortAudio and tkinter must be installed.

**Ubuntu:**

```apt-get install python3-tk```

```apt-get install portaudio19-dev python-all-dev```


Install the dependencies:

```python3 -m pip install -r requirements.txt```

Run the program:

```python3 audio_modder.py```


### MacOS
PortAudio and Python must be installed.

**Python**

Install [Python](https://www.python.org/downloads/macos/).

**PortAudio**

Install [Homebrew package manager](https://brew.sh/).

Install portaudio:

```brew install portaudio```



Install the dependencies:

```python3 -m pip install -r requirements.txt```

Run the program:

```python3 audio_modder.py```
