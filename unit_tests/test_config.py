import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import config
import pickle

class Foo:

    game_data_path: str
    last_loaded_archive: str

def generate_defect_config():
    invalid_path_config = config.Config(
        "E:/Program Files/Steam/steamapps/common/Helldivers 2/data",
        "D:/Unknown"
    )
    malformed_config = Foo()
    with open("invalid_path_config.pickle", "wb") as f:
        pickle.dump(invalid_path_config, f)
    with open("malformed_config.pickle", "wb") as f:
        pickle.dump(malformed_config, f)

if __name__ == "__main__":
    generate_defect_config()
    print("Testing malformed config")
    assert(config.load_config("malformed_config.pickle") is None)

    print("\nTesting basic control flow")
    cfg = config.load_config()
    assert(cfg != None and 
          cfg.game_data_path.endswith("steamapps/common/Helldivers 2/data") and 
          os.path.exists(cfg.game_data_path))
