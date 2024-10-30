"""
ext_register: A %-block extension for writing peripheral registers
"""

from .ext_percent import PercentBlockExtensionBase
import xml.etree.ElementTree as etree
import textwrap
import re

def colon_parse(text):
    RE_HEADER = re.compile(r'^(\S[^\n]*[^\\]):\s*$', re.MULTILINE)

    # Split into lines, each line ending with an unescaped colon is a group
    groups = re.split(RE_HEADER, text)
    groups = [ x.strip() for x in groups if x.strip() ]
    register, bits, *fields = groups

    # Group the field descriptions in pairs
    fields2 = { fields[i]: fields[i+1] for i in range(0, len(fields), 2) }

    # Parse bits
    bits = [ attr.strip().split(":") for attr in bits.split("\n") ]
    bits = { attr[0]: attr[1].strip() for attr in bits }

    return register, bits, fields2

class Spec:
    def __init__(self, spec):
        spec = spec.split()

        if len(spec) == 2:
            name = ""
            mode, default = spec
        else:
            name, mode, default = spec

        self.name = name
        self.mode = mode
        self.default = default[1:]

    def __repr__(self):
        return f"<'{self.name}' {self.mode} ={self.default}>"

class Register:
    def __init__(self, header, bits, fields):
        name, size = header.split()
        self.name = name
        self.size = {"u32": 32, "u16": 16, "u8": 8}[size]
        self.wide = False

        default = Spec("R =0")
        if "." in bits:
            default = Spec(bits["."])
            del bits["."]
        self.default = default

        def interval(e):
            try:
                return (int(e), 1)
            except ValueError:
                start, end = map(int, e.split("-"))
                if start > end:
                    start, end = end, start
                return (start, end - start + 1)
        def start(e):
            return interval(e)[0]
        def length(e):
            return interval(e)[1]
        def interval_or_name(f):
            try:
                return interval(f)
            except:
                return f

        bits = { start(e): (length(e), bits[e]) for e in bits }
        fields = { interval_or_name(f): fields[f] for f in fields }

        # Fill in intervals that are taken from either [default] or [bits]
        self.intervals = []
        b = 0

        while b < self.size:
            # Fill in with a gap until next bit entry
            gap = 0
            while b + gap < self.size and b + gap not in bits:
                gap += 1

            if gap > 0:
                self.intervals.append((gap, default, ""))
                b += gap
            if b >= self.size:
                break

            if b in bits:
                length2 = bits[b][0]
                spec = Spec(bits[b][1])

                # Check if there is a field description
                descr = ""
                for f in fields:
                    if f == (b, length2) or f == spec.name:
                        descr = fields[f]
                        break

                self.intervals.append((length2, Spec(bits[b][1]), descr))
                b += bits[b][0]

        self.intervals = list(reversed(self.intervals))

    def required_space(self, bits, spec, descr=None):
        text_space = len(spec.name)
        mode_space = len(spec.mode)
        normal_space = 4 * bits - 1
        return max(text_space, mode_space, normal_space)

    def has_default(self):
        return any(spec.name == "" for bits, spec, descr in self.intervals)

    def diagram(self):
        table = etree.Element("table")
        table.set("class", "register-diagram")

        bitnos = etree.SubElement(table, "tr")
        for i in reversed(range(self.size)):
            td = etree.SubElement(bitnos, "td")
            td.text = str(i)

        names = etree.SubElement(table, "tr")
        for bits, spec, descr in self.intervals:
            td = etree.SubElement(names, "td")
            td.text = spec.name
            if spec.name == "":
                td.set("class", "nothing")
            td.set("colspan", str(bits))

        initial = etree.SubElement(table, "tr")
        for bits, spec, descr in self.intervals:
            default = spec.default
            while len(default) < bits:
                default += spec.default
            for i in range(bits):
                td = etree.SubElement(initial, "td")
                td.text = default[i]
                if default[i] == "0" and not spec.name:
                    td.text = ""

        modes = etree.SubElement(table, "tr")
        for bits, spec, descr in self.intervals:
            mode = spec.mode
            if mode == "R" and not spec.name:
                mode = ""
            for i in range(bits):
                td = etree.SubElement(modes, "td")
                td.text = mode

        return table

    def table(self, parser):
        table = etree.Element("table")
        table.set("class", "register-bits tc1 tc2 tc3 tc4")
        if self.wide:
            table.set("class", table.get("class", "") + " wide")
        header = etree.SubElement(table, "tr")
        for h in ["Bits", "Name", "RW", "Init", "Description"]:
            th = etree.SubElement(header, "th")
            if h == "RW":
                code = etree.SubElement(th, "code")
                code.text = h
            else:
                th.text = h

        position = self.size - 1
        for bits, spec, descr in self.intervals:
            if not spec.name:
                position -= bits
                continue

            tr = etree.SubElement(table, "tr")
            td_bits  = etree.SubElement(tr, "td")
            td_name  = etree.SubElement(tr, "td")
            td_mode  = etree.SubElement(tr, "td")
            td_init  = etree.SubElement(tr, "td")
            td_descr = etree.SubElement(tr, "td")

            if bits == 1:
                td_bits.text = str(position)
            else:
                td_bits.text = str(position) + "-" + str(position - bits + 1)

            td_name.text = spec.name
            td_mode.text = spec.mode
            td_init.text = spec.default

            if descr:
                descr = textwrap.dedent("  " + descr)
                # TODO: Register processor: avoid block split heuristic?
                parser.parseBlocks(td_descr, descr.split("\n\n"))

            position -= bits

        return table

class PercentRegisterExtension(PercentBlockExtensionBase):
    BLOCK_NAMES = ["register"]
    def run(self, name, params, parent, content_blocks, parser):
        # Block boundaries are relevant, but not *all* of them, only those
        # inside descriptions.
        contents = "\n\n".join(content_blocks)
        name = params.get("name", None)
        desc = params.get("desc", None)
        wide = params.get("wide", False)

        header, bits, fields = colon_parse(contents)

        reg = Register(header, bits, fields)
        reg.wide = wide

        if name or desc:
            p = etree.SubElement(parent, "p")
            if name:
                e = etree.SubElement(p, "span")
                e.set("class", "register")
                e.text = name
                if desc:
                    e.tail = " " + desc
            elif desc:
                p.text = desc
        parent.append(reg.diagram())
        if fields:
            parent.append(reg.table(parser))
