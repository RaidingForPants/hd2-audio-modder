Setup() {
    python3 -m venv .venv
    
    source .venv/activate.ps1

    wget "https://github.com/vgmstream/vgmstream-releases/releases/download/nightly/vgmstream-linux-cli.tar.gz"

    tar -zxvf vgmstream-linux-cli.tar.gz

    rm vgmstream-linux-cli.tar.gz
    
    pip install -r requirements.txt
    
    deactivate
}

Build() {
    source .venv/activate.ps1

    python3 setup.py build
}
