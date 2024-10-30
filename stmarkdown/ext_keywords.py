"""
ext_keywords: Inline keyword highlighting extension.

This extension provides a simple mechanism for highlighting plain text keywords
with a CSS class. For example, replacing every occurrence of `TODO` with the
tag `<span class="todo">TODO</span>` and then use the stylesheet.

Usage: add `KeywordsExtension(keywords)` where `keywords: dict[str, str]` is
a dictionary of keywords to identify and the CSS class to add. For instance,
`{ "TODO": "todo" }` in the example above.
"""

from markdown.inlinepatterns import InlineProcessor
from markdown.extensions import Extension
import xml.etree.ElementTree as etree
import re

class KeywordsInlineProcessor(InlineProcessor):
    def __init__(self, pattern, md, keywords):
        super().__init__(pattern, md)
        self.keywords = keywords

    def handleMatch(self, m, data):
        el = etree.Element("span")
        if not m[0] in self.keywords:
            raise Exception(f"internal error: matched wrong keyword {m[0]}")
        el.set("class", self.keywords[m[0]])
        el.text = m[0]
        return el, m.start(0), m.end(0)

class KeywordsExtension(Extension):
    def __init__(self, keywords, **kwargs):
        self.keywords = keywords
        super().__init__(**kwargs)

    def extendMarkdown(self, md):
        md.registerExtension(self)
        pattern = r'|'.join(re.escape(k) for k in self.keywords.keys())
        md.inlinePatterns.register(KeywordsInlineProcessor(pattern, md, self.keywords), "keywords", 175)
