# Audio and Text Modder For Helldivers 2

I made this program to help make modding audio data easier.

[Mini tutorial for audio modding](https://docs.google.com/document/d/e/2PACX-1vT5mFXlk0iPGF-yoR3hMPrws3iPa4cY5O6PjzLcgz3Jj9vHUh5mYN1P1uWb6QiPA8K5rcvac929icV2/pub)

Thanks to everyone behind the [Helldivers 2 Blender Addon](https://github.com/Boxofbiscuits97/HD2SDK-CommunityEdition) for letting me use some of their code.

EXE built with PyInstaller and provided for convenience. If you are on Linux or MacOS you can run the Python code

## Running the Python code

You will need the appropriate distribution of vgmstream to play audio.

### Windows
Install Python 3. make sure to check in the Python installer the optional feature "tcl/tk and IDLE".

Install the dependencies:

```python -m pip install -r requirements.txt```

### Linux
PortAudio and tkinter must be installed.

**Ubuntu:**

```apt-get install python3-tk```

```apt-get install portaudio19-dev python-all-dev```


Install the dependencies:

```python3 -m pip install -r requirements.txt```
