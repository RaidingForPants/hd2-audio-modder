source ./.venv/bin/activate

pyinstaller ./audio_modder.py --onefile

cp ./azure.tcl ./dist
cp -r ./theme ./dist

deactive
