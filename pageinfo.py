#==============================================================================#
#     .;.      silent-tower docs                                               #
#    [ |*]     A simple documentation generator with lots of manual control.   #
#  .-=\|/=-.   License: MIT <https://mit-license.org/>                         #
#==============================================================================#
"""
Main data structure tracking metadata and relative paths for pages.
"""

import xml.etree.ElementTree as etree
import dataclasses
import os
import stdoc.collect # typing only
from stdoc.util import *
from typing import Tuple

# Info for a single source file representing a generated page.
@dataclasses.dataclass
class PageInfo:
    # Bundle owning this page. This affects all config settings.
    bundle: "stdoc.collect.Bundle"
    # Page ID. This is used to identify multiple versions of the same page in
    # different languages. This also serves as the URL (modulo language and
    # .html) unless there is an URL override.
    id: str
    # Page language code (e.g. "en", "fr", ...)
    lang: str
    # URL override, as specified by file metadata
    url_override: Url | None = None

    # Template to be used for rendering
    template: str = "base.html"
    # Relative path from global static folder to page's local static folder
    local_static: Url = Url("/")

    # Page title (affects DOCGEN_TITLE macro)
    title: str = ""
    # Label namespace in which non-absolute labels in the file will be defined
    label_namespace: str = ""
    # All labels defined with file; the key is an absolute label name.
    # TODO: Stronger definition for what label targets can be.
    labels: dict[str, Url] = dataclasses.field(default_factory=dict)

    # Intermediate document/fragment trees, generated by Python-Markdown
    # in-between parsing and post-processing when we resolve inter-page refs.
    tree: etree.Element | None = None
    fragments: dict[str, etree.Element] | None = None

    def config(self, query, default=None):
        return self.bundle.config(query, default)

    # Generate the components of the default URL as a triplet:
    #   1: Language prefix, such as "/en", "/fr", or ""
    #   2: Path, which is just the ID prefixed with /, e.g. "/page"
    #   3: Suffix, which can be ".html", "index.html", or ""
    def _url_components(self, force_suffix: bool = False) -> \
            Tuple[str, str, str]:
        lang = "/" + self.lang if self.config("languages", False) else ""
        path = "/" + self.id
        suffix = ""
        if force_suffix or self.config("urls.html_suffix"):
            suffix = "index.hml" if path.endswith("/") else ".html"
        return lang, path, suffix

    def _default_url(self, *, lang: bool, suffix: bool,
                     force_suffix: bool = False) -> Url:
        lang_str, path, suffix_str = self._url_components(force_suffix)
        if not lang:
            lang_str = ""
        if not suffix:
            suffix_str = ""
        return Url((lang_str * lang) + path + (suffix_str * suffix))

    def _overridden_url(self, *, force_suffix: bool = False) -> Url:
        url = self.url_override
        assert url is not None
        if force_suffix or self.config("urls.html_suffix"):
            return url.addHtmlSuffix()
        return url

    def url(self) -> Url:
        if self.url_override:
            return self._overridden_url()
        else:
            return self._default_url(lang=True, suffix=True)

    def output_path(self) -> str:
        if self.url_override:
            url = self._overridden_url(force_suffix=True)
        else:
            url = self._default_url(lang=True, suffix=True, force_suffix=True)
        s = str(url)
        assert s.startswith("/")
        assert s.endswith(".html")
        return os.path.join(self.config("outputs.folder", "_www"), s[1:])

    # Relative path to other URL
    def relpath(self, target: Url) -> str:
        return target % self.url()

    def localStaticUrl(self) -> Url:
        return self.local_static
    def localStaticRelpath(self) -> str:
        return self.localStaticUrl() % self.url()
    def globalStaticRelpath(self) -> str:
        return Url("/static") % self.url()

    # Add a label
    def add_label(self, name, target):
        assert not name.startswith("@")
        name = self.label_namespace + ":" + name
        if name in self.labels:
            err(f"multiple definitions of label {name}; overriding to '{target}'")
        self.labels[name] = target
