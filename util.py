#==============================================================================#
#     .;.      silent-tower docs                                               #
#    [ |*]     A simple documentation generator with lots of manual control.   #
#  .-=\|/=-.   License: MIT <https://mit-license.org/>                         #
#==============================================================================#
"""
Utility functions independent of any application logic.
"""

from typing import Iterable, Any
import sys
import os

def print_nonl(*args, **kwargs):
    print(*args, **kwargs, end="")
    sys.stdout.flush()
    sys.stdout.buffer.write(b"\r\x1b[K")

def warn(*args, **kwargs):
    print("\x1b[33mwarning:\x1b[0m ", end="")
    print(*args, **kwargs)

def err(*args, **kwargs):
    print("\x1b[31merror:\x1b[0m ", end="")
    print(*args, **kwargs)

def print_with_guard(s: str, guard: str) -> None:
    lines = s.splitlines()
    print("\n".join(guard + s for s in lines))

def style(s: str, style_spec: str) -> str:
    if not style_spec:
        return s
    styles = {
        "B": "1", "D": "2", "I": "3", "U": "4",
        "k": "30", "r": "31", "g": "32", "y": "33", "b": "34", "m": "35",
        "c": "36",
    }
    before = ""
    for c in style_spec:
        if c in styles:
            before += "\x1b[" + styles[c] + "m"

    return before + s + "\x1b[0m"

def termlen(s: str) -> int:
    l = 0
    in_escape = False
    for c in s:
        if c == "\x1b":
            in_escape = True
        l += not in_escape
        if in_escape and c == "m":
            in_escape = False
    return l

def termljust(s: str, n: int) -> str:
    return s.ljust(n + len(s) - termlen(s))

def recursive_mkdir(fpath: str) -> None:
    if not fpath or os.path.exists(fpath):
        return
    recursive_mkdir(os.path.dirname(fpath))
    try:
        os.mkdir(fpath)
    except FileExistsError:
        pass

# This function takes a list/iterable of paths as input, which should be sorted
# or grouped by a traversal order, and then returns a tree dictionary of the
# paths as in the filesystem and full paths as values. For example, given
# ["a", "b/c", "b/d", "e", "f/g/h"], this function returns:
#
#   {"a": "a",
#    "b/": {"c": "b/c",
#           "d": "b/d"},
#    "e": "e",
#    "f/": {"g/": {"h": "f/g/h"}}}
#
# Folders may be distinguished from files with .endswith("/").
def nest_paths(paths: Iterable[str]) -> dict[str, Any]:
    def traverse(org, i, prefix, result):
        while i < len(org) and org[i].startswith(prefix):
            suffix = org[i][len(prefix):]
            if "/" not in suffix:
                result[suffix] = org[i]
                i += 1
            else:
                subdir = suffix[:suffix.index("/")+1]
                result[subdir] = dict()
                i = traverse(org, i, prefix + subdir, result[subdir])
        return i

    r: dict[str, Any] = dict()
    traverse(paths, 0, "", r)
    return r

# This function is similar to nest_paths(), but it nests by depth, returning a
# flat list of mixed files and folders all annotated with their depth. It
# yields triplets (depth: int, name: str, origin: str | None) where origin is
# the full path for file and None for folders. Given the example input
# ["a", "b/c", "b/d", "e", "f/g/h"], this function yields:
#
# -> (0, "a", "a")
# -> (0, "b/", None)
# -> (1, "c", "b/c")
# -> (1, "d", "b/d")
# -> (0, "e", "e")
# -> (0, "f/", None)
# -> (1, "g/", None)
# -> (1, "h", "f/g/h")
def nest_paths_by_depth(paths):
    def aux(dic, depth):
        for key, value in dic.items():
            if key.endswith("/"):
                yield (depth, key, None)
                yield from aux(value, depth+1)
            else:
                yield (depth, key, value)
    yield from aux(nest_paths(paths), 0)

# Path abstractions.
#
# Paths must:
# 1. Begin with a "/". This is because in no-filename URL style "/" is a valid
#    URL and we don't want to represent it with the empty string.
# 2. Not end with a "/", unless the entire path is "/".
#
# Input paths are interpreted relative to the main bundle's folder.
# URLs are interpreted relative to the (unspecified) root URL relative to which
# the documentation will be deployed.

class AbstractPath:
    _path: str

    def __init__(self, path: str):
        AbstractPath.assertValid(path)
        self._path = path

    def __str__(self) -> str:
        return self._path

    def _join(self, subpath: str) -> str:
        return os.path.join(self._path, subpath)

    def _relpath(self, target: str) -> str:
        """Relative path to another path. While this is a relative path, its
           structure is always the same: enough "../" to go back to the root,
           then add the target path. This is fairly simple and works around an
           issue where browsers interpret ".." relative to "x/y" to be "x/"
           with an extra slash, which is not how we want page URLs to look."""
        AbstractPath.assertValid(target)

        # Start by removing the file name part of the path, otherwise it gets
        # interpreted as a folder by relpath(). There's always a file name
        # unless the path is "/", which is itself unaffected by dirname().
        base = os.path.dirname(self._path)
        AbstractPath.assertValid(base)

        # Now find how many "../" to go back to the root and join that with the
        # path to the target.

        # If target is "/", return the ".."-path. We'll get a "/" at the end of
        # the target URL once interpreter by browser. Such is life. (We can't
        # avoid that without knowing the full root URL.)
        if target == "/":
            result = os.path.relpath("/", base)
        # If base is "/", skip the join to avoid a needless "./".
        elif base == "/":
            result = target[1:]
        # Otherwise, join normally.
        else:
            root = os.path.relpath("/", base)
            result = os.path.join(root, target[1:])

        # print(style("<relpath>", "U"), self._path, "(" + base + ")", target,
        #     "->", result)
        return result

    @staticmethod
    def assertValid(path: str) -> None:
        if not path.startswith("/"):
            raise Exception("invalid path: {}".format(path))
        if path != "/" and path.endswith("/"):
            raise Exception("invalid path: {}".format(path))

class InputPath(AbstractPath):
    def __mod__(self, base: "InputPath") -> str:
        assert isinstance(base, InputPath)
        return base._relpath(self._path)

    def __truediv__(self, subdir: str) -> "InputPath":
        return InputPath(self._join(subdir))

class Url(AbstractPath):
    def __mod__(self, base: "Url") -> str:
        assert isinstance(base, Url)
        return base._relpath(self._path)

    def __truediv__(self, subdir: str) -> "Url":
        return Url(self._join(subdir))

    def addHtmlSuffix(self) -> "Url":
        path = self._path
        path += "index.html" if path.endswith("/") else ".html"
        return Url(path)
