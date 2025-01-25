function Setup() {
    python -m venv .venv
    
    . .venv/Scripts/Activate.ps1
    
    wget -Uri "https://github.com/vgmstream/vgmstream-releases/releases/download/nightly/vgmstream-win64.zip" -OutFile vgmstream-win64.zip
    
    Expand-Archive -Path "vgmstream-win64.zip" -DestinationPath "vgmstream-win64"
    
    rm vgmstream-win64.zip
    
    pip install -r requirements.txt
    
    deactivate
}

function Build() {
    . .venv/Scripts/Activate.ps1

    python setup.py build

    $compress = @{
        Path = "build/exe.win-amd64-3.12/*"
        CompressionLevel = "Fastest"
        DestinationPath = "release.zip"
    }

    Compress-Archive @compress

    deactivate
}

function Clean() {
    rm build
}
