import os
import pathlib

from const import SUPPORTED_AUDIO_TYPES


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
            if ext in SUPPORTED_AUDIO_TYPES or "patch" in ext:
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


def to_posix(path: str):
    return pathlib.PurePath(path).as_posix()
