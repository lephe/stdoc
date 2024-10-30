#==============================================================================#
#     .;.      silent-tower docs                                               #
#    [ |*]     A simple documentation generator with lots of manual control.   #
#  .-=\|/=-.   License: MIT <https://mit-license.org/>                         #
#==============================================================================#
"""
Collection tools for finding input files and their metadata

This module implements the collection phase where stdoc searches for bundles,
input files, static files, then parses the input files to extract their
metadata, and builds the skeleton of the output tree, including assigning final
URLs to all pages.
"""

import os
import glob
import yaml
import fnmatch
import stdoc.stmarkdown
from enum import Enum
from typing import Iterable, Union, Any
from dataclasses import dataclass, field

from stdoc.pageinfo import *
from stdoc.util import *

# TODO: Internal flag to enable debugging the filesystem search
_DEBUG_FSS = False

def filesystemSearch(dirpath: str, fss: dict[str, Any],
                     ignoreSubpaths: list[str] = []) -> list[str]:
    def toStringList(x: None | str | list[str]) -> list[str]:
        if x is None:
            return []
        if isinstance(x, str):
            return [x]
        return x
    def splitAll(path: str) -> list[str]:
        x, y = os.path.split(path)
        if x == "" or y == "":
            return [x + y]
        return splitAll(x) + [y]
    def debugPrint(*args, **kwargs):
        if _DEBUG_FSS:
            print("[fss] ", end="")
            print(*args, **kwargs)

    # First, find input globs from match_files or match_paths.
    matchGlobs = []
    for mf in toStringList(fss.get("match_files")):
        matchGlobs.append(os.path.join(dirpath, "**", mf))
    for mp in toStringList(fss.get("match_paths")):
        matchGlobs.append(os.path.join(dirpath, mp))
    debugPrint(f"{matchGlobs=}")

    # Run those globs.
    candidates = set()
    for mg in matchGlobs:
        candidates.update(glob.glob(mg, recursive=True))

    # Exclude anything that's captured by exclude patterns.
    matches = set()
    for c in candidates:
        assert c.startswith(dirpath + "/")
        c = c[len(dirpath)+1:]
        comps = splitAll(c)
        assert comps != []
        keep = True
        for ef in toStringList(fss.get("exclude_folders")):
            if fnmatch.fnmatch(comps[0], ef):
                debugPrint(f"ignoring {c} because exclude_folders {ef}")
                keep = False
        for ef in toStringList(fss.get("exclude_files")):
            if fnmatch.fnmatch(comps[-1], ef):
                debugPrint(f"ignoring {c} because exclude_files {ef}")
                keep = False
        for isp in ignoreSubpaths:
            isp = isp.rstrip("/") + "/" # FIXME
            if c.startswith(isp):
                debugPrint(f"ignoring {c} because subfolder {isp}")
                keep = False
        if keep:
            matches.add(c)

    debugPrint(f"({len(matches)}) {matches=}")
    return sorted(matches)

class Bundle:
    _dir: str
    _config: dict[str, Any]
    _subdirs: dict[str, "Bundle"]
    _statics: list[str]
    _parent: Union[None, "Bundle"]
    _pages: dict[str, PageInfo] | None

    def __init__(self, dirpath):
        """Builds the bundle by parsing its `stdoc.conf`. Raises an exception
           if `stdoc.conf` doesn't exist or is invalid. The subdirs are listed
           in `inputs.bundles` and should be loaded by the caller (to handle
           their exceptions separately) then added with `registerSubdir()`."""
        try:
            with open(os.path.join(dirpath, "stdoc.conf")) as fp:
                self._config = yaml.safe_load(fp.read())
                # Empty file
                if self._config is None:
                    self._config = dict()
        except FileNotFoundError as e:
            raise Exception("{}: not a bundle no (stdoc.conf)".format(dirpath))

        self._dir = dirpath
        self._subdirs = dict()
        self._parent = None
        self._pages = None

    def _log(self, *args, **kwargs):
        print(style("[{}] ".format(self._dir), "m"), end="")
        print(*args, **kwargs)

    def config(self, query: str = "", default: Any = None) -> Any:
        """Queries the config with a dot-path like "key.subkey.field". The
           default value is returned if the field or any parent is missing."""
        def lookup(dic: dict[str, Any], fields: list[str], i: int) -> Any:
            if i >= len(fields):
                return (True, dic)
            if fields[i] not in dic:
                return (False, default)
            return lookup(dic[fields[i]], fields, i+1)
        def lookupInBundle(b: Bundle):
            found, value = lookup(b._config, fields, 0)
            if not found and b._parent is not None:
                return lookupInBundle(b._parent)
            return value
        fields = query.split(".") if query else []
        return lookupInBundle(self)

    def registerSubdir(self, subdir: str, bundle: "Bundle") -> None:
        """Registers a bundle loaded from a subfolder (at any depth)."""
        self._subdirs[subdir] = bundle
        bundle._parent = self

    def iterBundles(self) -> Iterable["Bundle"]:
        """Yields this bundle and all sub-bundles, recursively, depth-first."""
        yield self
        for sb in self._subdirs.values():
            yield from sb.iterBundles()

    def iterParents(self) -> Iterable["Bundle"]:
        yield self
        if self._parent is not None:
            yield from self._parent.iterParents()

    def _findPages(self) -> list[str]:
        fss = self.config("inputs.pages")
        if fss is None:
            warn("{}: no inputs.pages".format(self._dir))
            return []
        return filesystemSearch(self._dir, fss, list(self._subdirs.keys()))

    def checkLangSuffix(self, path: str) -> Tuple[str, str | None]:
        """Checks whether the file named in the given path has a language
           suffix as listed in the `languages` config key. If so, split it and
           return `(path without suffix, lang)`. Otherwise, returns `(original
           path, None)`."""
        path = os.path.normpath(os.path.join(self._dir, path))
        dirname, filename = os.path.split(path)
        basename = os.path.splitext(filename)[0]
        if self.config("inputs.lang_suffix", False):
            for lang in self.config("languages", dict()):
                if basename.endswith("-" + lang):
                    return os.path.join(dirname, basename[:-len(lang)-1]), lang
        return os.path.join(dirname, basename), None

    def loadPages(self) -> None:
        """Finds all pages within this bundle, excluding sub-bundles. The
           search result is cached for later calls."""
        if self._pages is not None:
            return
        self._pages = dict()

        for path in self._findPages():
            id, lang = self.checkLangSuffix(path)
            if lang is None:
                lang = self.config("language", "en")
            p = PageInfo(bundle=self, id=id, lang=lang)
            self._pages[os.path.normpath(os.path.join(self._dir, path))] = p

        self._log("loaded {} source files".format(len(self._pages)))

        self._statics = filesystemSearch(self._dir,
            {"match_files": "_static"}, list(self._subdirs.keys()))
        self._statics = [os.path.dirname(path)
                         for path in self._statics if os.path.isdir(path)]
        self._log("static folders: {}".format(self._statics))

    def pages(self) -> dict[str, PageInfo]:
        assert self._pages is not None
        return self._pages

    def pagesRecursively(self) -> dict[str, PageInfo]:
        pages: dict[str, PageInfo] = dict()
        for b in self.iterBundles():
            pages.update(**b.pages())
        return pages

    def includeRoot(self) -> str:
        return self._dir

    def labelNamespace(self) -> str:
        # TODO: Lack of testing for sub-bundles in nested subdirs
        if self._dir == ".":
            return ""
        return ":" + self._dir.replace("/", ":")

    def localStaticFromPath(self, path: str) -> str:
        # Just pull the path to a _static folder with the longest common prefix
        path = os.path.normpath(path)
        best = ""
        for static in self._statics:
            if path.startswith(static) and len(static) > len(best):
                best = static
        return best

def loadBundle(dirpath, recursive=False):
    try:
        b = Bundle(dirpath)
    except Exception as e:
        err("{}: cannot load bundle (skipping)".format(dirpath))
        print_with_guard(str(e), style("| ", "r"))
        return None
    if recursive:
        for subdirpath in b.config("inputs.bundles", []):
            sb = loadBundle(subdirpath, recursive)
            if sb is not None:
                b.registerSubdir(subdirpath, sb)
    return b

def initialParse(mainBundle, md):
    allPages = mainBundle.pagesRecursively()

    for i, (path, p) in enumerate(allPages.items()):
        print_nonl(f"[{i+1}/{len(allPages)}] Parsing {path}...")
        with open(path, "r") as fp:
            source = fp.read()

        p.label_namespace = p.bundle.labelNamespace()
        md.ext_include_root = p.bundle.includeRoot()
        p.tree = stdoc.stmarkdown.preprocess_parse_treeprocess(md, source)
        p.fragments = md.fragments

        # Analyze the metadata block
        fileLabels = []
        for key, value in md.Meta.items():
            if key == "title" and len(value) == 1:
                p.title = value[0]
            elif key == "url" and len(value) == 1:
                url = value[0]
                if url.endswith(".html"):
                    print("{}: URL override {} should omit '.html' suffix" \
                        .format(path, url))
                    url = url[:-5]
                if not url.startswith("/"):
                    # TODO: Make URL override be relative to bundle
                    url = "/" + url
                p.url_override = Url(url)
            elif key == "lang" and len(value) == 1:
                p.lang = value[0]
            elif key == "template" and len(value) == 1:
                p.template = value[0]
            elif key == "label":
                assert all(v.startswith("@") for v in value)
                fileLabels.extend(value)
            else:
                warn(f"{path}: unknown metadata '{key}' of length {len(value)}")

        # Collect labels
        for l in fileLabels:
            p.add_label(l[1:], p.url())

@dataclass
class IDInfo:
    # Bundle that this ID is searched in.
    bundle: Bundle
    # All pages that have this ID in the bundle.
    pages: list[PageInfo] = field(default_factory=list)
    # Sorted list of all languages that appear in `pages`.
    lang: list[str] = field(default_factory=list)

    # Display string for language list
    str_lang: str = ""
    # Display string for URLs
    str_url: str = ""
    # All labels
    str_labels: str = ""

    def __init__(self, bundle: Bundle, id: str):
        pages = [p for p in bundle.pages().values() if p.id == id]
        self.bundle = bundle
        self.pages = sorted(pages, key=lambda p: p.lang)
        self.lang = [p.lang for p in pages]

        self.str_lang = ", ".join(style(lang, "c") for lang in self.lang)

        # Try and give a single URL pattern for all pages with this ID. Usually
        # the URLs only differ by language prefix, but we check it rather than
        # assume it, just in case.
        url_components = [p._url_components() for p in pages]
        url_defaults = all(p.url_override is None for p in pages)
        # Path and suffix must match on all versions of the page
        url_uniform = all(comps[1:] == url_components[0][1:]
                          for comps in url_components)

        if url_uniform and url_defaults:
            self.str_url = "/" + style("<lang>", "c") \
                + url_components[0][1] + style(url_components[0][2], "wD")
        else:
            strs = []
            for p in pages:
                if p.url_override is not None:
                    s = "{} ({})".format(style(str(p.url()),"y"),
                                         style(str(p.lang),"c"))
                else:
                    comp = p._url_components()
                    s = style(comp[0], "c") + comp[1] + style(comp[2], "wD")
                strs.append(s)
            self.str_url = ", ".join(strs)

        labels_by_language: dict[str, set[str]] = dict()
        for p in self.pages:
            for l in p.labels:
                if l not in labels_by_language:
                    labels_by_language[l] = set()
                labels_by_language[l].add(p.lang)

        strs = []
        for l, langs in labels_by_language.items():
            if len(langs) == len(self.pages):
                strs.append(style(l, "g"))
            else:
                str_l = ", ".join(style(lang, "c") for lang in langs)
                strs.append(style(l, "g") + " (" + str_l + ")")
        self.str_labels = ", ".join(strs)

def summaryTable(mainBundle):
    # Take bundles in depth-first order, which is a good-looking tree.
    bundles = list(mainBundle.iterBundles())
    # Each group contains the pages from one particular bundle.
    groups = []
    # Info for each ID; mostly precomputed strings to display in the table.
    idinfo = dict()

    for b in bundles:
        ids = sorted({p.id for p in b.pages().values()})
        for id in ids:
            # Ensure there is only one bundle using the ID
            assert id not in idinfo
            idinfo[id] = IDInfo(b, id)
        nested = list(nest_paths_by_depth(ids))
        groups.append(nested)

    # TODO: Ensure there is only one page per lang/ID pair

    # Compute the width needed for each column
    headings = ["Bundle", "ID", "Lang", "URL", "Labels"]
    sizes = [len(h) for h in headings]

    for nested in groups:
        for (depth, name, org) in nested:
            sizes[1] = max(sizes[1], 2 * depth + len(name))
            if org is not None:
                info = idinfo[org]
                sizes[0] = max(sizes[0], len(info.bundle._dir))
                sizes[2] = max(sizes[2], termlen(info.str_lang))
                sizes[3] = max(sizes[3], termlen(info.str_url))
                sizes[4] = max(sizes[4], termlen(info.str_labels))

    # Print table header
    print("\x1b[47;30;1m ", end="")
    print("   ".join(h.ljust(sz) for h, sz in zip(headings, sizes)), end="")
    print(" \x1b[0m")

    # Print table
    for bundle, nested in zip(bundles, groups):
        firstLine = True
        for (depth, name, org) in nested:
            str_bundle, lang, url, labels = "", "", "", ""
            if firstLine:
                str_bundle = bundle._dir
                firstLine = False
            else:
                str_bundle = "|"
            if org is not None:
                info = idinfo[org]
                lang = info.str_lang
                url = info.str_url
                labels = info.str_labels

            print(" ", end="")
            print(style(str_bundle.rjust(sizes[0]), "m"), end = " │ ")
            print("  " * depth + style(name.ljust(sizes[1] - 2 * depth),
                "bB" if org is None else ""), end=" │ ")

            print(termljust(lang, sizes[2]), end=" │ ")
            print(termljust(url, sizes[3]), end=" │ ")
            print(termljust(labels, sizes[4]), end=" \n")
