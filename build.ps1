. .\.venv\Scripts\Activate.ps1

pyinstaller .\audio_modder.py --onefile

cp .\azure.tcl .\dist
cp -r .\theme .\dist
cp -r .\AudioConversionTemplate .\dist

wget -Uri "https://github.com/Dekr0/hd2_audio_db/releases/download/v.0.0.1-alpha/hd_audio_db.db" -OutFile .\dist\hd_audio_db.db
wget -Uri "https://github.com/vgmstream/vgmstream-releases/releases/download/nightly/vgmstream-win64.zip" -OutFile .\dist\vgmstream-win64.zip

Expand-Archive -Path ".\dist\vgmstream-win64.zip" -DestinationPath ".\dist\vgmstream-win64"

rm .\dist\vgmstream-win64.zip

deactivate
