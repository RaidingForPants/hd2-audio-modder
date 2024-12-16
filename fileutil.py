import os
import pathlib

from const_global import SYSTEM

class INode:

    def __init__(self, isdir: bool, absolute_path: str, basename: str):
        self.absolute_path: str = absolute_path
        self.basename: str = basename
        self.isdir = isdir
        self.nodes: list[INode] = []

def generate_file_tree(path) -> INode | None:
    if not os.path.exists(path):
        return None
    inodes: dict[str, INode] = {}
    for dirpath, dirnames, filenames in os.walk(path):
        curr = None
        if dirpath not in inodes:
            curr = INode(True, dirpath, os.path.basename(dirpath))
            inodes[dirpath] = curr
        else:
            curr = inodes[dirpath]
        for dirname in dirnames:
            absolute_path = os.path.join(dirpath, dirname)
            inode = INode(True, absolute_path, dirname) 
            inodes[absolute_path] = inode
            curr.nodes.append(inode)
        for filename in filenames:
            _, ext = os.path.splitext(filename)
            if ext in [".wav", ".wem"] or "patch" in ext:
                curr.nodes.append(INode(
                    False, os.path.join(dirpath, filename), filename))
                
    return inodes[path]

def traverse(node):
    stack: list[INode] = [node]
    while len(stack) > 0:
        top = stack.pop()
        for node in top.nodes:
            if node.isdir:
                stack.append(node)


def list_files_recursive(path="."):
    files = []
    if os.path.isfile(path):
        return [path]
    else:
        for entry in os.listdir(path):
            full_path = os.path.join(path, entry)
            if os.path.isdir(full_path):
                files.extend(list_files_recursive(full_path))
            else:
                files.append(full_path)
        return files

def std_path(p: str):
    match SYSTEM:
        case "Windows":
            return pathlib.PureWindowsPath(p).as_uri()
        case "Linux" | "Darwin":
            return pathlib.PurePosixPath(p).as_uri()
        case _:
            return pathlib.Path(p).as_uri()
