"""
ext_percent: Base mechanism for writing custom blocks.

This module provides a simple block processor for writing percent-delimited
blocks with a name and parameters (kind of like reStructuredText directives).

TODO: Document the percent block processor.
"""

from markdown.blockprocessors import BlockProcessor
from markdown.extensions import Extension
import re

class PercentBlockProcessor(BlockProcessor):
    RE_INTRO = re.compile(r'^(%+)(\w[\w_.-]*)[ ]*(?:\(([^\n]+)\))?[ ]*(?:\n|(%)$)', re.MULTILINE)
    RE_PARAM = re.compile(r'([a-z]+)=(?:([^\s"]+)|"((?:[^"]|\\")*)")(?=\s|$)')

    def __init__(self, md):
        super().__init__(md)
        self.block_types = dict()

    def addBlockType(self, name, handler):
        if name in self.block_types:
            raise Exception(f"%-block conflict for '{name}'")
        self.block_types[name] = handler

    def test(self, parent, block):
        return self.RE_INTRO.match(block)

    def run(self, parent, blocks):
        m = self.RE_INTRO.match(blocks[0])
        assert m is not None
        delimiter = m[1]
        name = m[2]
        params = self.parse_params(m[3])
        blocks[0] = blocks[0][m.end(0):]

        # Grab block contents until we find a %-line that marks the end. If
        # m[4] is non-empty there are no contents so stop immediately.
        content_blocks = []
        i = 0
        while m[4] is None and i < len(blocks):
            lines = blocks[i].split("\n")
            if delimiter in lines:
                delimiter_index = lines.index(delimiter)
                content_blocks.append("\n".join(lines[:delimiter_index]))
                blocks[i] = "\n".join(lines[delimiter_index+1:])
                break
            else:
                content_blocks.append(blocks[i])
                del blocks[i]

        # print(f"Percent block: type {name}, params {params}")
        if name not in self.block_types:
            raise Exception(f"no %-block extension for '{name}'")

        return self.block_types[name](name, params, parent, content_blocks, self.parser)

    def parse_params(self, param_str):
        index = 0
        params = dict()
        while param_str:
            param_str = param_str.strip()
            m = self.RE_PARAM.match(param_str)
            if not m:
                raise Exception(f"invalid %-block params: '{param_str}'")
            param_str = param_str[len(m[0]):]
            params[m[1]] = m[2] or m[3].encode("raw_unicode_escape").decode("unicode_escape")
        return params

class PercentBlockCoreExtension(Extension):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def extendMarkdown(self, md):
        md.registerExtension(self)
        self.proc = PercentBlockProcessor(md.parser)
        md.parser.blockprocessors.register(self.proc, 'percent_block', 175)

    def addBlockType(self, name, handler):
        self.proc.addBlockType(name, handler)

class PercentBlockExtensionBase(Extension):
    BLOCK_NAMES: list[str]

    def run(self, name, params, parent, content_blocks, parser):
        raise NotImplementedError("should be subsclassed")

    def extendMarkdown(self, md):
        # Find the PercentBlockCoreExtension and add ourselves to it
        for ext in md.registeredExtensions:
            if isinstance(ext, PercentBlockCoreExtension):
                for name in self.BLOCK_NAMES:
                    ext.addBlockType(name, self.run)
                return
        raise Exception("missing a PercentBlockCoreExtension()")
