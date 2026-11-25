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
# Report
# --------------------------------------------------------------------------
def _status(count):
    return "OK" if count == 0 else f"CHECK ({count})"


def render(result):
    r = result
    lines = ["# Thesis check report", ""]
    lines += [
        f"- Reference entries in the draft: **{r['n_references']}**",
        f"- Entries in the RIS export: **{r['n_ris'] if r['n_ris'] is not None else 'not checked'}**",
        f"- Citation marks found in the text: **{r['n_citation_marks']}** "
        f"(covering {len(r['cited_numbers'])} different references)",
        "",
        "| Check | Result |",
        "|---|---|",
        f"| Citations pointing to a missing reference (error) | {_status(len(r['missing']))} |",
        f"| References never cited | {_status(len(r['uncited']))} |",
        f"| References first cited out of order | {_status(len(r['out_of_order']))} |",
        f"| Gaps in the reference numbering | {_status(len(r['gaps']))} |",
        f"| Duplicate reference entries | {_status(len(r['duplicates']))} |",
    ]
    if r["n_ris"] is not None:
        count_mismatch = 0 if r["n_ris"] == r["n_references"] else 1
        lines += [
            f"| Draft and RIS have the same number of entries | {_status(count_mismatch)} |",
            f"| RIS entries not found in the draft's list | {_status(len(r['ris_missing_in_draft']))} |",
            f"| Draft references not found in the RIS | {_status(len(r['draft_missing_in_ris']))} |",
        ]
    lines += [
        f"| Unresolved [TO BE CONFIRMED] markers | {_status(len(r['placeholders']))} |",
        f"| Paragraphs still marked as expected values | {_status(len(r['expected']))} |",
        "",
    ]

    def section(title, rows):
        if rows:
            lines.extend([f"## {title}", ""] + rows + [""])

    section("Citations pointing to a missing reference",
            [f"- ({n}) is cited but there is no reference {n}" for n in r["missing"]])
    section("References never cited",
            [f"- {n}. {r['references'][n][:110]}" for n in r["uncited"]])
    section("References first cited out of order",
            [f"- Reference {n} is first cited after reference {m} ({sec})"
             for n, m, sec in r["out_of_order"]])
    section("Gaps in the reference numbering", [f"- {n}" for n in r["gaps"]])
    section("Possible duplicate references",
            [f"- Entries {a} and {b} look nearly identical" for a, b in r["duplicates"]])
    section("RIS entries not found in the draft's list", [f"- {t}" for t in r["ris_missing_in_draft"]])
    section("Draft references not found in the RIS",
            [f"- {n}. {r['references'][n][:110]}" for n in r["draft_missing_in_ris"]])

    if r["placeholders"]:
        by_section = {}
        for sec, marker in r["placeholders"]:
            by_section.setdefault(sec, []).append(marker)
        rows = []
        for sec, markers in by_section.items():
            rows.append(f"**{sec}** ({len(markers)})")
            rows += [f"- {m[:140]}" for m in markers]
            rows.append("")
        section("Unresolved [TO BE CONFIRMED] markers", rows)

    section("Still marked as expected values (replace with measured data)",
            [f"- **{sec}**: {text}" for sec, text in r["expected"]])
    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(description="Check the VMAT-TBI thesis draft.")
    parser.add_argument("--docx", default=str(DEFAULT_DOCX), help="thesis draft (.docx)")
    parser.add_argument("--ris", default=str(DEFAULT_RIS), help="RIS reference export")
    parser.add_argument("--out", help="also write the report to this Markdown file")
    parser.add_argument("--strict", action="store_true", help="exit with 1 on any warning")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    paragraphs = read_paragraphs(args.docx)
    ris = read_ris(args.ris) if Path(args.ris).exists() else None
    result = analyse(paragraphs, ris)
    report = render(result)
    print(report)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")

    errors, warnings = errors_and_warnings(result)
    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
