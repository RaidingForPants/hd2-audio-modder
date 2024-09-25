import os

class INode:

    def __init__(self, isdir: bool, absolute_path: str, basename: str):
        self.absolute_path: str = absolute_path
        self.basename: str = basename
        self.isdir = isdir
        self.nodes: list[INode] = []

def generate_file_tree(root_path) -> INode | None:
    if not os.path.exists(root_path):
        return None
    root = INode(True, root_path, os.path.basename(root_path))
    stack: list[INode] = [root]
    while len(stack) > 0:
        top = stack.pop()
        if not os.path.exists(top.absolute_path):
            continue
        for dirpath, dirnames, filenames in os.walk(top.absolute_path):
            for dirname in dirnames:
                inode = INode(True, os.path.join(dirpath, dirname), dirname)
                top.nodes.append(inode)
                stack.append(inode)
            for filename in filenames:
                ext = filename.split(".")
                if ext[-1] == "wem":
                    top.nodes.append(INode(
                        False, os.path.join(dirpath, filename), filename))
    return root
