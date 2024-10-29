source ./.venv/bin/activate

pyinstaller ./audio_modder.py --onefile

cp ./azure.tcl ./dist
cp -r ./theme ./dist
cp -r ./AudioConversionTemplate ./dist

wget "https://github.com/Dekr0/hd2_audio_db/releases/download/v.0.0.1-alpha/hd_audio_db.db" -O ./dist/hd_audio_db.db

wget "https://github.com/vgmstream/vgmstream-releases/releases/download/nightly/vgmstream-win64.zip" -O ./dist/vgmstream-win64.zip
mkdir ./dist/vgmstream-win64
unzip ./dist/vgmstream-win64.zip -d ./dist/vgmstream-win64
rm ./dist/vgmstream-win64.zip

deactive
