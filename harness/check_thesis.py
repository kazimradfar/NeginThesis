#!/usr/bin/env python3
"""Thesis check harness for the VMAT-based TBI M.Sc. thesis.

Reads the Word draft and the RIS reference export and reports:

  1. citations that point to a reference number that does not exist
  2. references that are never cited
  3. references whose first citation is out of numeric order
  4. differences between the reference list in the draft and the RIS export
  5. unresolved "[TO BE CONFIRMED]" markers, grouped by section
  6. paragraphs/tables still marked as holding expected (not measured) values

Standard library only. It runs offline and needs no API key.

Usage (from the repository root):
    python harness/check_thesis.py
    python harness/check_thesis.py --out harness/report.md
    python harness/check_thesis.py --lang fa --out harness/report.fa.md   # Persian report
    python harness/check_thesis.py --docx "path/to/draft.docx" --ris "path/to/refs.ris"

Exit code: 1 if a citation points to a missing reference (or, with --strict,
if any warning is found); otherwise 0.

Known limit: a numbered list written as "(1) ... (2) ..." in the body text looks
like a citation and can show up as a false positive.
"""

import argparse
import difflib
import html
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DOCX = ROOT / "Full Draft" / "VMAT-TBI_MSc_Thesis_Full_Draft.docx"
DEFAULT_RIS = ROOT / "Reference" / "VMAT-TBI_thesis_references.ris"

PARA = re.compile(r"<w:p[ >].*?</w:p>", re.S)
STYLE = re.compile(r'<w:pStyle w:val="([^"]+)"')
TOKEN = re.compile(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>|<w:tab\s*/>|<w:br\s*/>")

CITE = re.compile(r"\((\d{1,3}(?:\s*[,–—-]\s*\d{1,3})*)\)")
REF_LINE = re.compile(r"^(\d{1,3})\.\s*(.+)$", re.S)
PLACEHOLDER = re.compile(r"\[TO BE CONFIRMED[^\]]*\]", re.I)
EXPECTED = re.compile(r"expected values|replace with measured", re.I)


@dataclass
class Paragraph:
    style: str
    text: str


# --------------------------------------------------------------------------
# Reading the inputs
# --------------------------------------------------------------------------
def read_paragraphs(docx_path):
    """Return the visible paragraphs of a .docx (table of contents skipped)."""
    xml = zipfile.ZipFile(docx_path).read("word/document.xml").decode("utf-8")
    paragraphs = []
    for raw in PARA.findall(xml):
        m = STYLE.search(raw)
        style = m.group(1) if m else ""
        if style.upper().startswith("TOC") or "PAGEREF" in raw:
            continue
        parts = []
        for tok in TOKEN.finditer(raw):
            if tok.group(1) is not None:
                parts.append(html.unescape(tok.group(1)))
            elif tok.group(0).startswith("<w:tab"):
                parts.append("\t")
            else:
                parts.append("\n")
        text = "".join(parts).strip()
        if text:
            paragraphs.append(Paragraph(style, text))
    return paragraphs


def read_ris(ris_path):
    """Return a list of {'TI': title, 'AU': [authors], 'PY': year} dicts."""
    entries, cur = [], None
    text = Path(ris_path).read_text(encoding="utf-8-sig")
    for line in text.splitlines():
        m = re.match(r"^([A-Z][A-Z0-9])  - ?(.*)$", line)
        if not m:
            continue
        tag, val = m.groups()
        if tag == "TY":
            cur = {"TI": "", "AU": [], "PY": ""}
        elif tag == "ER":
            if cur is not None:
                entries.append(cur)
            cur = None
        elif cur is not None:
            if tag == "AU":
                cur["AU"].append(val)
            elif tag in ("TI", "T1") and not cur["TI"]:
                cur["TI"] = val
            elif tag in ("PY", "Y1") and not cur["PY"]:
                cur["PY"] = val[:4]
    return entries


# --------------------------------------------------------------------------
# Parsing helpers
# --------------------------------------------------------------------------
def heading_level(style):
    m = re.match(r"(?i)^heading\s*(\d)$", style or "")
    return int(m.group(1)) if m else None


def expand_citation(group):
    """'3-5' -> [3, 4, 5]; '7, 12' -> [7, 12]; '5' -> [5]."""
    numbers = []
    for part in re.split(r"\s*,\s*", group.strip()):
        ends = re.split(r"\s*[–—-]\s*", part)
        if len(ends) == 2 and int(ends[0]) <= int(ends[1]) <= int(ends[0]) + 50:
            numbers.extend(range(int(ends[0]), int(ends[1]) + 1))
        else:
            numbers.extend(int(x) for x in ends)
    return numbers


def norm(text):
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _references_start(paragraphs):
    """Index of the last paragraph that is just the word 'References'."""
    index = None
    for i, p in enumerate(paragraphs):
        if p.text.strip().lower() in ("references", "bibliography"):
            index = i
    return index


# --------------------------------------------------------------------------
# The checks
# --------------------------------------------------------------------------
def analyse(paragraphs, ris_entries=None):
    start = _references_start(paragraphs)
    body = paragraphs[:start] if start is not None else paragraphs
    ref_paragraphs = paragraphs[start + 1:] if start is not None else []

    references = {}
    for p in ref_paragraphs:
        m = REF_LINE.match(p.text)
        if m:
            references[int(m.group(1))] = m.group(2).strip()

    stack = {}
    cited = []          # (number, section) in reading order
    n_marks = 0         # how many "(..)" citation marks there are
    placeholders = []   # (section, marker text)
    expected = []       # (section, start of paragraph)
    for p in body:
        level = heading_level(p.style)
        if level:
            stack = {k: v for k, v in stack.items() if k < level}
            stack[level] = p.text
            continue
        section = " > ".join(stack[k] for k in sorted(stack)) or "(front matter)"
        for m in CITE.finditer(p.text):
            n_marks += 1
            for n in expand_citation(m.group(1)):
                cited.append((n, section))
        for m in PLACEHOLDER.finditer(p.text):
            placeholders.append((section, m.group(0)))
        if EXPECTED.search(p.text):
            expected.append((section, p.text[:160]))

    cited_numbers = {n for n, _ in cited}
    missing = sorted(n for n in cited_numbers if n not in references)
    uncited = sorted(n for n in references if n not in cited_numbers)

    out_of_order, seen, max_seen = [], set(), 0
    for n, section in cited:
        if n in seen or n not in references:
            continue
        seen.add(n)
        if n < max_seen:
            out_of_order.append((n, max_seen, section))
        else:
            max_seen = n

    gaps = []
    if references:
        gaps = [n for n in range(1, max(references) + 1) if n not in references]

    ref_norm = {n: norm(t) for n, t in references.items()}
    # Near-identical full entries only: several reports by the same author
    # (for example different ICRU reports) must not count as duplicates.
    duplicates = []
    items = sorted(ref_norm.items())
    for i, (a, text_a) in enumerate(items):
        for b, text_b in items[i + 1:]:
            sm = difflib.SequenceMatcher(None, text_a, text_b)
            if (sm.real_quick_ratio() >= 0.92 and sm.quick_ratio() >= 0.92
                    and sm.ratio() >= 0.92):
                duplicates.append((a, b))

    ris_missing_in_draft, draft_missing_in_ris = [], []
    if ris_entries is not None:
        ris_titles = [norm(e["TI"]) for e in ris_entries]
        for e, t in zip(ris_entries, ris_titles):
            found = bool(t) and any(t in rn or t[:40] in rn for rn in ref_norm.values())
            if not found:
                first = e["AU"][0] if e["AU"] else "?"
                ris_missing_in_draft.append(f'{first} ({e["PY"] or "n.d."}): {e["TI"][:90]}')
        for n, rn in sorted(ref_norm.items()):
            found = any(t and (t in rn or t[:40] in rn) for t in ris_titles)
            if not found:
                draft_missing_in_ris.append(n)

    return {
        "n_references": len(references),
        "n_ris": None if ris_entries is None else len(ris_entries),
        "n_citation_marks": n_marks,
        "cited_numbers": sorted(cited_numbers),
        "missing": missing,
        "uncited": uncited,
        "out_of_order": out_of_order,
        "gaps": gaps,
        "duplicates": duplicates,
        "ris_missing_in_draft": ris_missing_in_draft,
        "draft_missing_in_ris": draft_missing_in_ris,
        "placeholders": placeholders,
        "expected": expected,
        "references": references,
    }


def errors_and_warnings(result):
    errors = len(result["missing"])
    warnings = (
        len(result["uncited"]) + len(result["out_of_order"]) + len(result["gaps"])
        + len(result["duplicates"]) + len(result["ris_missing_in_draft"])
        + len(result["draft_missing_in_ris"]) + len(result["placeholders"])
        + len(result["expected"])
    )
    if result["n_ris"] is not None and result["n_ris"] != result["n_references"]:
        warnings += 1
    return errors, warnings


# --------------------------------------------------------------------------
# Report (English and Persian)
# --------------------------------------------------------------------------
STRINGS = {
    "en": {
        "title": "Thesis check report",
        "refs_draft": "Reference entries in the draft",
        "refs_ris": "Entries in the RIS export",
        "not_checked": "not checked",
        "marks": "Citation marks found in the text: **{marks}** "
                 "(covering {distinct} different references)",
        "th": ("Check", "Result"),
        "ok": "OK",
        "check": "CHECK ({n})",
        "front": "(front matter)",
        "row_missing": "Citations pointing to a missing reference (error)",
        "row_uncited": "References never cited",
        "row_order": "References first cited out of order",
        "row_gaps": "Gaps in the reference numbering",
        "row_dups": "Duplicate reference entries",
        "row_count": "Draft and RIS have the same number of entries",
        "row_ris_missing": "RIS entries not found in the draft's list",
        "row_draft_missing": "Draft references not found in the RIS",
        "row_placeholders": "Unresolved [TO BE CONFIRMED] markers",
        "row_expected": "Paragraphs still marked as expected values",
        "sec_missing": "Citations pointing to a missing reference",
        "ln_missing": "- ({n}) is cited but there is no reference {n}",
        "sec_uncited": "References never cited",
        "sec_order": "References first cited out of order",
        "ln_order": "- Reference {n} is first cited after reference {m} ({sec})",
        "sec_gaps": "Gaps in the reference numbering",
        "sec_dups": "Possible duplicate references",
        "ln_dups": "- Entries {a} and {b} look nearly identical",
        "sec_ris_missing": "RIS entries not found in the draft's list",
        "sec_draft_missing": "Draft references not found in the RIS",
        "sec_placeholders": "Unresolved [TO BE CONFIRMED] markers",
        "sec_expected": "Still marked as expected values (replace with measured data)",
    },
    "fa": {
        "title": "گزارش بررسی پایان‌نامه",
        "refs_draft": "تعداد منابع در پیش‌نویس",
        "refs_ris": "تعداد منابع در فایل RIS",
        "not_checked": "بررسی نشد",
        "marks": "ارجاع‌های موجود در متن: **{marks}** (مربوط به {distinct} منبع متفاوت)",
        "th": ("بررسی", "نتیجه"),
        "ok": "بدون مشکل",
        "check": "نیاز به بررسی ({n})",
        "front": "(صفحات ابتدایی)",
        "row_missing": "ارجاع به منبعی که وجود ندارد (خطا)",
        "row_uncited": "منابعی که در متن ارجاع داده نشده‌اند",
        "row_order": "منابعی که ترتیب اولین ارجاعشان به‌هم ریخته است",
        "row_gaps": "جاافتادگی در شماره‌گذاری منابع",
        "row_dups": "منابع تکراری",
        "row_count": "تعداد منابع پیش‌نویس و RIS یکسان است",
        "row_ris_missing": "منابع RIS که در فهرست پیش‌نویس نیستند",
        "row_draft_missing": "منابع پیش‌نویس که در RIS نیستند",
        "row_placeholders": "موارد [TO BE CONFIRMED] حل‌نشده",
        "row_expected": "بخش‌هایی که هنوز مقدار مورد انتظار دارند",
        "sec_missing": "ارجاع به منبع ناموجود",
        "ln_missing": "- ارجاع ({n}) داده شده اما منبع شماره {n} وجود ندارد",
        "sec_uncited": "منابع بدون ارجاع در متن",
        "sec_order": "منابعی که ترتیب اولین ارجاعشان به‌هم ریخته است",
        "ln_order": "- منبع {n} پس از منبع {m} برای اولین بار ارجاع داده شده است ({sec})",
        "sec_gaps": "جاافتادگی در شماره‌گذاری منابع",
        "sec_dups": "منابع احتمالاً تکراری",
        "ln_dups": "- منابع {a} و {b} تقریباً یکسان هستند",
        "sec_ris_missing": "منابع RIS که در فهرست پیش‌نویس پیدا نشدند",
        "sec_draft_missing": "منابع پیش‌نویس که در RIS پیدا نشدند",
        "sec_placeholders": "موارد [TO BE CONFIRMED] حل‌نشده",
        "sec_expected": "هنوز مقدار مورد انتظار دارند (باید با داده‌های اندازه‌گیری‌شده جایگزین شوند)",
    },
}


def render(result, lang="en"):
    """Render the Markdown report. Section names from the thesis stay in English."""
    r, T = result, STRINGS[lang]

    def status(count):
        return T["ok"] if count == 0 else T["check"].format(n=count)

    ris_count = r["n_ris"] if r["n_ris"] is not None else T["not_checked"]
    lines = [
        f"# {T['title']}", "",
        f"- {T['refs_draft']}: **{r['n_references']}**",
        f"- {T['refs_ris']}: **{ris_count}**",
        "- " + T["marks"].format(marks=r["n_citation_marks"], distinct=len(r["cited_numbers"])),
        "",
        f"| {T['th'][0]} | {T['th'][1]} |",
        "|---|---|",
    ]

    def row(key, count):
        lines.append(f"| {T['row_' + key]} | {status(count)} |")

    row("missing", len(r["missing"]))
    row("uncited", len(r["uncited"]))
    row("order", len(r["out_of_order"]))
    row("gaps", len(r["gaps"]))
    row("dups", len(r["duplicates"]))
    if r["n_ris"] is not None:
        row("count", 0 if r["n_ris"] == r["n_references"] else 1)
        row("ris_missing", len(r["ris_missing_in_draft"]))
        row("draft_missing", len(r["draft_missing_in_ris"]))
    row("placeholders", len(r["placeholders"]))
    row("expected", len(r["expected"]))
    lines.append("")

    def section(title, rows):
        if rows:
            lines.extend([f"## {title}", ""] + rows + [""])

    refs = r["references"]
    section(T["sec_missing"], [T["ln_missing"].format(n=n) for n in r["missing"]])
    section(T["sec_uncited"], [f"- {n}. {refs[n][:110]}" for n in r["uncited"]])
    section(T["sec_order"], [T["ln_order"].format(n=n, m=m, sec=sec)
                             for n, m, sec in r["out_of_order"]])
    section(T["sec_gaps"], [f"- {n}" for n in r["gaps"]])
    section(T["sec_dups"], [T["ln_dups"].format(a=a, b=b) for a, b in r["duplicates"]])
    section(T["sec_ris_missing"], [f"- {t}" for t in r["ris_missing_in_draft"]])
    section(T["sec_draft_missing"], [f"- {n}. {refs[n][:110]}" for n in r["draft_missing_in_ris"]])

    if r["placeholders"]:
        by_section = {}
        for sec, marker in r["placeholders"]:
            by_section.setdefault(sec.replace("(front matter)", T["front"]), []).append(marker)
        rows = []
        for sec, markers in by_section.items():
            rows.append(f"**{sec}** ({len(markers)})")
            rows += [f"- {m[:140]}" for m in markers]
            rows.append("")
        section(T["sec_placeholders"], rows)

    section(T["sec_expected"], [f"- **{sec}**: {text}" for sec, text in r["expected"]])

    body = "\n".join(lines).rstrip() + "\n"
    if lang == "fa":
        body = '<div dir="rtl" align="right">\n\n' + body + "\n</div>\n"
    return body


# --------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(description="Check the VMAT-TBI thesis draft.")
    parser.add_argument("--docx", default=str(DEFAULT_DOCX), help="thesis draft (.docx)")
    parser.add_argument("--ris", default=str(DEFAULT_RIS), help="RIS reference export")
    parser.add_argument("--out", help="also write the report to this Markdown file")
    parser.add_argument("--strict", action="store_true", help="exit with 1 on any warning")
    parser.add_argument("--lang", choices=sorted(STRINGS), default="en",
                        help="report language: en (English) or fa (Persian); default en")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    paragraphs = read_paragraphs(args.docx)
    ris = read_ris(args.ris) if Path(args.ris).exists() else None
    result = analyse(paragraphs, ris)
    report = render(result, args.lang)
    print(report)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")

    errors, warnings = errors_and_warnings(result)
    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
