#==============================================================================#
#     .;.      silent-tower docs                                               #
#    [ |*]     A simple documentation generator with lots of manual control.   #
#  .-=\|/=-.   License: MIT <https://mit-license.org/>                         #
#==============================================================================#
"""
A simple documentation generator with knobs for manual control.
"""

import os
import re
import sys
import shutil
import stdoc.stmarkdown
import stdoc.collect
from typing import Tuple
from stdoc.util import *

USAGE = """\
stdoc -- a simple documentation generator
usage: stdoc <folder>
"""

def usage(exitcode):
    print(USAGE, end="")
    return exitcode

def main(argv):
    if "-h" in argv or "--help" in argv:
        return usage(0)
    if len(argv) != 2:
        return usage(1)

    # FIXME: Paths and IDs should be relative to argv[1], not CWD.

    mainBundle = stdoc.collect.loadBundle(argv[1], recursive=True)
    if mainBundle is None:
        return 1

    # Find pages in all loaded bundles
    for b in mainBundle.iterBundles():
        b.loadPages()

    # Parse input files to get their metadata and assign their URLs
    md = stdoc.stmarkdown.make_Markdown()
    stdoc.collect.initialParse(mainBundle, md)
    stdoc.collect.summaryTable(mainBundle)

    # TODO: Extract more labels than just page label
    # + error if there are multiple definitions of the same label
    # + warn if language variants don't define the same labels!

    # Link pages together to resolve inter-page references
    pages = mainBundle.pagesRecursively()
    crossref_pages(pages)

    # Generate final HTML output (this also does some reference resolution)
    generate_html(mainBundle, pages, md)

    # Also copy static files
    print("Copying static files")
    for b in mainBundle.iterBundles():
        for static in b._statics:
            src = os.path.join(b._dir, static, "_static")
            dst = os.path.join(b.config("outputs.folder"), "static", b._dir, static)
            print(" ", src, "->", dst)
            shutil.copytree(src, dst, dirs_exist_ok=True)

    files = mainBundle.config("inputs.files")
    if files is not None:
        print("Copying raw files")
        for ff in stdoc.collect.filesystemSearch(".", files):
            print(" ", ff, "->", mainBundle.config("outputs.folder"))
            shutil.copytree(ff, mainBundle.config("outputs.folder"),
                            dirs_exist_ok=True)

#---
# Cross-file referencing and patching
#---

unresolved_labels = set()

def resolve_label(pages, sourcePage, label, lang) -> Tuple[Url | None, str]:
    # Relative to absolute path
    if not label.startswith(":"):
        label = sourcePage.label_namespace + ":" + label
    found = []
    for p in pages.values():
        if p.lang is not None and lang is not None and p.lang != lang:
            continue
        for l, target in p.labels.items():
            if l == label:
                found.append((target, p.title))
    if len(found) == 0:
        unresolved_labels.add(label)
        return None, ""
    elif len(found) > 1:
        err(f"multiple definitions of label @{label} found")
    return found[0]

def replace_url(p, url, pages):
    if url is None:
        return None, None, None
    if url.startswith("="):
        return p.relpath(p.localStaticUrl() / url[1:]), None, None
    if url.startswith("=:"):
        return p.relpath(p.globalStaticUrl() / url[2:]), None, None
    if url.startswith("@"):
        target, title = resolve_label(pages, p, url[1:], p.lang)
        if target is None:
            return None, None, None
        else:
            return p.relpath(target), url, title
    return url, None, None

def patch_static_urls(p, tree, pages):
    for a in tree.iterfind(".//a"):
        new_url, old_text, new_text = replace_url(p, a.get("href"), pages)
        if new_url is None:
            a.attrib.pop("href")
            a.set("class", "broken")
        else:
            a.set("href", new_url)
            if a.text == old_text:
                a.text = new_text
    for img in tree.iterfind(".//img"):
        img.set("src", replace_url(p, img.get("src"), pages))

# Patch URLs in the Markdown trees
def crossref_pages(pages):
    for path, p in pages.items():
        inputStatic = p.bundle.localStaticFromPath(path)
        urlStatic = os.path.join("/static", p.bundle._dir, inputStatic)
        p.local_static = Url(os.path.normpath(urlStatic))
        patch_static_urls(p, p.tree, pages)
        for frag in p.fragments.values():
            patch_static_urls(p, frag, pages)

    if len(unresolved_labels):
        err("there were unresolved labels")
        for l in sorted(unresolved_labels):
            print(f"  @{l}")

# Finally, write out all resulting files to the _www folder. During the post-
# processing step we apply a variable replacement scheme for {DOCGEN_*} to
# modify the HTML (which we can't parse, it's not XML). This applies to raw
# HTML blocks and thus most template code. It's not ideal but it works.

def tree_to_html(md, tree, variables):
    html = stdoc.stmarkdown.serialize_postprocess(md, tree)
    regex = r'{{[ ]*(%s)[ ]*}}' % '|'.join(variables)
    return re.sub(regex, lambda m: variables[m[1]], html)

import jinja2

def makeRefFunction(pages, p):
    def ref(label):
        assert label.startswith("@")
        target, _ = resolve_label(pages, p, label[1:], p.lang)
        rp = p.relpath(target) if target is not None else None
        # print("<> from", p.url(), "target", label, "=", target, "->", rp)
        return rp
    return ref

def generate_html(mainBundle, pages, md):
    # One Jinja environment per bundle since the configuration may change.
    jenvs = dict()
    for b in mainBundle.iterBundles():
        templatePaths = [os.path.join(parent._dir, "_templates")
                         for parent in b.iterParents()]
        j = jinja2.Environment(
            loader=jinja2.FileSystemLoader(templatePaths),
            autoescape=jinja2.select_autoescape(),
            keep_trailing_newline=True)
        j.filters["langcode"] = lambda code: b.config("languages")[code]
        # j.filters["local"] = lambda text: "" if STRIP_HTML_SUFFIX else text
        jenvs[b] = j

    total_written = 0
    for i, p in enumerate(pages.values()):
        path = p.output_path()
        recursive_mkdir(os.path.dirname(path))

        print_nonl(f"[{i+1}/{len(pages)}] Writing out {path}...")
        with open(path, "w") as fp:
            variables = {
                "DOCGEN_GLOBAL_STATIC": p.globalStaticRelpath(),
                "DOCGEN_LOCAL_STATIC": p.localStaticRelpath(),
                "DOCGEN_ROOT": p.relpath(Url("/")),
                "DOCGEN_LANG": p.lang,
                "DOCGEN_TITLE": p.title,
            }

            body = tree_to_html(md, p.tree, variables)
            fragments = {
                "DOCGEN_FRAGMENT_" + name: tree_to_html(md, frag, variables)
                for name, frag in p.fragments.items() }

            lang = sorted((i.lang, i.url()) for i in pages.values() if i.id == p.id)

            template = jenvs[p.bundle].get_template(p.template)
            html = template.render(
                DOCGEN_ID = p.id,
                DOCGEN_DOC = p,
                DOCGEN_ARTICLE = body,
                DOCGEN_LANG_AVAILABLE = lang,
                ref = makeRefFunction(pages, p),
                static = lambda path: p.relpath(p.localStaticUrl() / path),
                global_static = lambda path: p.relpath(Url("/static") / path),
                **variables,
                **fragments)
            fp.write(html)
        total_written += 1

    print(f"Produced {total_written} pages")

sys.exit(main(sys.argv))
