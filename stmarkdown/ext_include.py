"""
ext_include: An extension for including other files verbatim

Pretty much like the C preprocessor. `..include "sth.md"` will include. A field
`.ext_include_root` can be set on the Markdown instance to control where we
include from.
"""

from markdown.preprocessors import Preprocessor
from markdown.extensions import Extension
from markdown.extensions.codehilite import parse_hl_lines
from typing import Tuple, Any
import re
import os

class IncludeExtension(Extension):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def extendMarkdown(self, md):
        md.registerExtension(self)
        md.preprocessors.register(IncludePreprocessor(md), 'include', 25)

class IncludePreprocessor(Preprocessor):
    RE_INCLUDE = re.compile(r'^\.\.include[ ]*\"([^"]+)\"[ ]*$')

    def run(self, lines):
        root = getattr(self.md, "ext_include_root", "")
        out_lines = []
        for l in lines:
            m = self.RE_INCLUDE.match(l)
            if m is not None:
                path = os.path.join(root, m[1])
                with open(path, "r") as fp:
                    out_lines.extend(self.run(fp.read().splitlines()))
            else:
                out_lines.append(l)
        return out_lines

    def handle_attrs(self, attrs) -> Tuple[str, list[str], dict[str, Any]]:
        id = ''
        classes = []
        configs: dict[str, Any] = {}
        for k, v in attrs:
            if k == 'id':
                id = v
            elif k == '.':
                classes.append(v)
            elif k == 'hl_lines':
                configs[k] = parse_hl_lines(v)
            elif k == 'linenums':
                configs[k] = True
            else:
                configs[k] = v
        return id, classes, configs
