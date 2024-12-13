def strip_patch_index(filename):
    split = filename.split(".")
    for n in range(len(split)):
        if "patch_" in split[n]:
            del split[n]
            break
    filename = ".".join(split)
    return filename
