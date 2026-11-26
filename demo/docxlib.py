"""Small helpers to edit the thesis .docx while keeping EndNote fields."""
import copy
import re

from docx.oxml.ns import qn

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def runs_of(p):
    return [c for c in p if c.tag == W + "r"]


def text_of(el):
    return "".join(t.text or "" for t in el.iter(W + "t"))


def field_groups(p):
    """Yield lists of consecutive child elements forming one complex field."""
    kids = list(p)
    i = 0
    while i < len(kids):
        k = kids[i]
        fc = k.find(W + "fldChar") if k.tag == W + "r" else None
        if fc is not None and fc.get(W + "fldCharType") == "begin":
            depth, j = 0, i
            while j < len(kids):
                f2 = kids[j].find(W + "fldChar") if kids[j].tag == W + "r" else None
                if f2 is not None:
                    t = f2.get(W + "fldCharType")
                    depth += 1 if t == "begin" else (-1 if t == "end" else 0)
                    if depth == 0:
                        break
                j += 1
            yield kids[i:j + 1]
            i = j + 1
        else:
            i += 1


def instr_of(group):
    return "".join(t.text or "" for el in group for t in el.iter(W + "instrText"))


def result_text(group):
    out, after = [], False
    for el in group:
        fc = el.find(W + "fldChar")
        if fc is not None and fc.get(W + "fldCharType") == "separate":
            after = True
            continue
        if after:
            out.append(text_of(el))
    return "".join(out)


class CiteCache:
    def __init__(self, body):
        self.cache = {}
        # first pass: citations in body text with the default font size,
        # second pass: any citation (tables, captions)
        for plain_only in (True, False):
            for p in body.iter(W + "p"):
                for g in field_groups(p):
                    if "EN.CITE" not in instr_of(g):
                        continue
                    if plain_only and any(e.find(W + "rPr/" + W + "sz") is not None for e in g):
                        continue
                    m = re.fullmatch(r"\((\d+)\)", result_text(g).strip())
                    if m and m.group(1) not in self.cache:
                        self.cache[m.group(1)] = [copy.deepcopy(e) for e in g]

    def get(self, n):
        g = self.cache[str(n)]
        return [copy.deepcopy(e) for e in g]


def make_run(text, rpr=None):
    r = __import__("lxml.etree", fromlist=["etree"]).SubElement.__self__ if False else None
    from lxml import etree
    r = etree.Element(W + "r")
    if rpr is not None:
        r.append(copy.deepcopy(rpr))
    t = etree.SubElement(r, W + "t")
    t.text = text
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return r


def clear_para(p, keep_ppr=True):
    for c in list(p):
        if keep_ppr and c.tag == W + "pPr":
            continue
        p.remove(c)


def strip_highlight(el):
    for h in list(el.iter(W + "highlight")):
        h.getparent().remove(h)


def _copy_size(rpr, run):
    """Give a copied citation run the font size of the surrounding text."""
    from lxml import etree
    sizes = [rpr.find(W + t) for t in ("sz", "szCs")]
    if all(x is None for x in sizes):
        return
    rp = run.find(W + "rPr")
    if rp is None:
        rp = etree.Element(W + "rPr")
        run.insert(0, rp)
    later = {W + t for t in ("highlight", "u", "effect", "bdr", "shd", "fitText", "vertAlign", "rtl",
                             "cs", "em", "lang", "eastAsianLayout", "specVanish", "oMath")}
    for x in sizes:
        if x is not None:
            old = rp.find(x.tag)
            if old is not None:
                rp.remove(old)
            nxt = next((c for c in rp if c.tag in later), None)
            if nxt is not None:
                nxt.addprevious(copy.deepcopy(x))
            else:
                rp.append(copy.deepcopy(x))


TOKEN = re.compile(r"\[\[(\d+)\]\]|\*\*(.+?)\*\*")


def fill_para(p, text, cites, rpr=None, bold_rpr=None):
    """Replace the content of paragraph p; [[N]] inserts citation field N,
    **x** writes x in bold."""
    clear_para(p)
    pos = 0
    for m in TOKEN.finditer(text):
        if m.start() > pos:
            p.append(make_run(text[pos:m.start()], rpr))
        if m.group(1):
            for e in cites.get(m.group(1)):
                if rpr is not None and e.tag == W + "r":
                    _copy_size(rpr, e)
                p.append(e)
        else:
            from lxml import etree
            br = copy.deepcopy(bold_rpr) if bold_rpr is not None else (
                copy.deepcopy(rpr) if rpr is not None else etree.Element(W + "rPr"))
            if br.find(W + "b") is None:
                pos = sum(1 for c in br if c.tag in (W + "rStyle", W + "rFonts"))
                br.insert(pos, etree.Element(W + "b"))
            p.append(make_run(m.group(2), br))
        pos = m.end()
    if pos < len(text):
        p.append(make_run(text[pos:], rpr))


def replace_text(p, old, new):
    """Replace text inside a paragraph across runs (outside fields).
    Returns True if replaced."""
    ts = [t for t in p.iter(W + "t")]
    full = "".join(t.text or "" for t in ts)
    i = full.find(old)
    if i < 0:
        return False
    # locate start node
    pos = 0
    start_node = None
    for t in ts:
        L = len(t.text or "")
        if start_node is None and i < pos + L:
            start_node, off = t, i - pos
            break
        pos += L
    remaining = len(old)
    first = True
    k = ts.index(start_node)
    while remaining > 0 and k < len(ts):
        t = ts[k]
        s = t.text or ""
        o = off if first else 0
        take = min(remaining, len(s) - o)
        if first:
            t.text = s[:o] + new + s[o + take:]
            first = False
        else:
            t.text = s[take:]
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        remaining -= take
        k += 1
    return True
