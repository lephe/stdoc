"""
ext_code: An extension for triple-backtick code blocks.

Similar to the official extension, with a few differences.
- Matches in a reasonable line-by-line way instead of joining and using a crazy
  multi-line regex.
- Supports attributes without braces, e.g. ```c linenums. Syntax highlighting
  in editors might not understand the braces.
"""

from markdown.preprocessors import Preprocessor
from markdown.extensions import Extension
from markdown.extensions.attr_list import get_attrs_and_remainder
from markdown.extensions.codehilite import CodeHilite, parse_hl_lines
from typing import Tuple, Any
import re

class FencedCodeExtension(Extension):
    def __init__(self, hilite_conf, **kwargs):
        self.hilite_conf = hilite_conf
        super().__init__(**kwargs)

    def extendMarkdown(self, md):
        md.registerExtension(self)
        md.preprocessors.register(FencedBlockPreprocessor(md, self.hilite_conf), 'fenced_code_block', 25)

class FencedBlockPreprocessor(Preprocessor):
    RE_FENCE = re.compile(r'(`{3,})[ ]*([\w#.+-]*)[ ]*([^\n]*)')

    def __init__(self, md, hilite_conf):
        super().__init__(md)
        self.codehilite_conf = hilite_conf

    def match_fence(self, lines, index):
        m = self.RE_FENCE.fullmatch(lines[index])
        start_index = index
        if not m:
            return index+1, (None, None, None, None, None)
        index += 1
        while index < len(lines) and lines[index] != m[1]:
            index += 1
        id, classes, config = self.handle_attrs(get_attrs_and_remainder(m[3])[0])
        code = "\n".join(lines[start_index+1:index])
        return index+1, (m[2], id, classes, config, code)

    def run(self, lines):
        out_lines = []
        index = 0

        while index < len(lines):
            # Is there a fenced block at the current line?
            next_index, (lang, id, classes, config, code) = self.match_fence(lines, index)
            if classes is None:
                classes = []
            if code is None:
                out_lines.append(lines[index])
                index += 1
                continue
            # print(f"Fenced block at line {index}: lang {repr(lang)}, id {repr(id)}, classes {classes}, config {config}, {next_index-index-2} lines of code")

            local_config = {
                **self.codehilite_conf,
                **config,
                # Pygments adds a suffix so we get "codehilitetable"
                "cssclass": " ".join(classes) + " codehilite" }

            highliter = CodeHilite(code,
                lang=lang,
                style=local_config.pop('pygments_style', 'default'),
                **local_config)

            code = highliter.hilite(shebang=False)
            out_lines.append(self.md.htmlStash.store(code))
            index = next_index

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
