from markdown import Markdown
from markdown.inlinepatterns import SubstituteTagPattern
from markdown.inlinepatterns import InlineProcessor
from markdown.extensions import Extension
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.toc import TocExtension
import xml.etree.ElementTree as etree

from .ext_code import FencedCodeExtension
from .ext_percent import PercentBlockCoreExtension, PercentBlockExtensionBase
from .ext_keywords import KeywordsExtension
from .ext_register import PercentRegisterExtension
from .ext_include import IncludeExtension

class HardBreakExtension(Extension):
    def extendMarkdown(self, md):
        BREAK_RE = r' *\\\\\n'
        breakPattern = SubstituteTagPattern(BREAK_RE, 'br')
        md.inlinePatterns.register(breakPattern, 'hardbreak', 185)

# A table extension that doesn't have fancy display/alignment features or a
# stylish syntax, but supports writing block content within cells.
class PercentTableExtension(PercentBlockExtensionBase):
    BLOCK_NAMES = ["table"]
    def run(self, name, params, parent, content_blocks, parser):
        rowsep = params.get("rowsep", "\\\\")
        colsep = params.get("colsep", "|")
        head   = params.get("head", "none")
        align  = params.get("align", "center")
        class_ = params.get("class", "")

        # We want to split at row/cell boundaries but currently certain cells
        # cross over multiple blocks. Join block first with an identifiable
        # marker (U+001D GROUP SEPARATOR), then split rows/cells, and later
        # re-split intra-cell blocks boundaries.
        contents = "\u001d".join(content_blocks)
        rows = [x.strip() for x in contents.split(rowsep) if x]

        table = etree.SubElement(parent, "table")
        if align == "center":
            table.set("style", "margin-left: auto; margin-right: auto")
        if class_:
            table.set("class", class_)

        for i, row in enumerate(rows):
            tr = etree.SubElement(table, "tr")
            for j, text in enumerate(row.strip().split(colsep)):
                cell_tag = "td"
                if head in ["row", "rowcol"] and i == 0:
                    cell_tag = "th"
                if head in ["col", "rowcol"] and j == 0:
                    cell_tag = "th"
                cell = etree.SubElement(tr, cell_tag)
                if text.strip():
                    parser.parseBlocks(cell, text.split("\u001d"))

class LabelInlineProcessor(InlineProcessor):
    def handleMatch(self, m, data):
        el = etree.Element("span")
        el.set("id", m[1])
        return el, m.start(0), m.end(0)

class LabelReferenceInlineProcessor(InlineProcessor):
    def handleMatch(self, m, data):
        el = etree.Element("a")
        el.set("href", m[0])
        el.text = m[0]
        return el, m.start(0), m.end(0)

class LabelsExtension(Extension):
    def extendMarkdown(self, md):
        md.registerExtension(self)
        # 125 is lower than links (170) so we don't substitue in URLs
        LABEL_PATTERN = r'@=([a-zA-Z0-9._]+)'
        md.inlinePatterns.register(LabelInlineProcessor(LABEL_PATTERN, md), "label-def", 125)
        REF_PATTERN = r'@([a-zA-Z0-9_.:]*[a-zA-Z0-9._])'
        md.inlinePatterns.register(LabelReferenceInlineProcessor(REF_PATTERN, md), "label-ref", 125)

class PercentFragmentExtension(PercentBlockExtensionBase):
    BLOCK_NAMES = ["fragment"]
    def run(self, name, params, parent, content_blocks, parser):
        name = params["name"]
        div = etree.Element("div")
        parser.parseBlocks(div, content_blocks)
        parser.md.fragments[name] = div

class PercentCenterExtension(PercentBlockExtensionBase):
    BLOCK_NAMES = ["center"]
    def run(self, name, params, parent, content_blocks, parser):
        p = etree.SubElement(parent, "p")
        p.set("style", "text-align: center")
        p.text = "\n\n".join(content_blocks)

# This extension allows links to be written as !!non-space-characters and
# globally set a prefix for what "!!" should expand to. The prefix is taken
# from document metadata.
class BangLinksInlineProcessor(InlineProcessor):
    def handleMatch(self, m, data):
        if "bang-links" not in self.md.Meta:
            el = etree.Element("span")
            el.set("style", "color: red")
            el.text = m[0]
        else:
            el = etree.Element("a")
            el.set("href", self.md.Meta["bang-links"][0].replace("{}", m[1]))
            el.set("title", m[1])
            text_pattern = self.md.Meta.get("bang-links-text", ["{}"])[0]
            el.text = text_pattern.replace("{}", m[1])
            # FIXME: Hack that should apply only to URLs
            if "{}" in text_pattern:
                el.set("style", "word-break: break-all")
        return el, m.start(0), m.end(0)

class BangLinksExtension(Extension):
    def extendMarkdown(self, md):
        md.registerExtension(self)
        pattern = r'!!((?:[.,;:)]*[^\s.,;:)])+)'
        md.inlinePatterns.register(BangLinksInlineProcessor(pattern, md), "banglinks", 180)

_keywords = {
    "???": "unknown",
    "TODO": "todo",
    "LIKELY": "likely",
    "CONFIRMED": "confirmed",
}

_md_opt = 0
_md_ext = [
  'tables', 'sane_lists', 'meta', 'attr_list', 'def_list', 'md_in_html',
  TocExtension(toc_depth="2-6"),
  CodeHiliteExtension(linenums=True, use_pygments=True),
  FencedCodeExtension({ "use_pygments": True }),
  HardBreakExtension(),
  PercentBlockCoreExtension(),
  PercentTableExtension(),
  LabelsExtension(),
  KeywordsExtension(_keywords),
  PercentRegisterExtension(),
  IncludeExtension(),
  PercentFragmentExtension(),
  PercentCenterExtension(),
  BangLinksExtension(),
]

def make_Markdown():
    return Markdown(options=_md_opt, extensions=_md_ext)

# This is a modified version of Markdown.convert split in two stages. First
# stage does the preprocessing, block parsing, and tree processing.
def preprocess_parse_treeprocess(md, source):
    md.fragments = dict()

    # Split into lines and run the line preprocessors.
    md.lines = source.split("\n")
    for prep in md.preprocessors:
        md.lines = prep.run(md.lines)

    # Parse the high-level elements.
    root = md.parser.parseDocument(md.lines).getroot()

    # Run the tree-processors
    for treeprocessor in md.treeprocessors:
        newRoot = treeprocessor.run(root)
        if newRoot is not None:
            root = newRoot
    for name, frag in md.fragments.items():
        for treeprocessor in md.treeprocessors:
            newFrag = treeprocessor.run(frag)
            if newFrag is not None:
                frag = newFrag
        md.fragments[name] = frag

    return root

# After we connect documents together, second stage does the serialization and
# the postprocessing.
def serialize_postprocess(md, tree):
    # Serialize _properly_.  Strip top-level tags.
    output = md.serializer(tree)
    if md.stripTopLevelTags:
        try:
            start = output.index('<%s>' % md.doc_tag) + len(md.doc_tag) + 2
            end = output.rindex('</%s>' % md.doc_tag)
            output = output[start:end].strip()
        except ValueError as e:
            if output.strip().endswith('<%s />' % md.doc_tag):
                # We have an empty document
                output = ''
            else:
                # We have a serious problem
                raise ValueError('Markdown failed to strip top-level '
                                 'tags. Document=%r' % output.strip()) from e

    # Run the text post-processors
    for pp in md.postprocessors:
        output = pp.run(output)

    return output.strip()
