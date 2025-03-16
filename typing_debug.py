"""
This is a script that is meant to run in a debugger. It's used for document 
types of different classes and variables
"""
from core import ModHandler, Mod

ModHandler.create_instance()
handler: ModHandler = ModHandler.get_instance()
handler.create_new_mod("Debugging")
mod: Mod = handler.get_active_mod()

mod.load_archive_file("D:/sfx/MG/patch/hmg/squad_dshk/0bdf199f7ac14f43.patch_0")
mod.load_archive_file("D:/sfx/MG/patch/hmg/squad_dshk/68e80476c1c602f5.patch_0")
mod.load_archive_file("D:/sfx/MG/patch/hmg/squad_dshk/902c54afb4ed396f.patch_0")
mod.load_archive_file("D:/Program Files/Steam/steamapps/common/Helldivers 2/data/2e24ba9dd702da5c")
