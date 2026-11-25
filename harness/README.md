# Thesis check harness

A small script that checks the thesis draft (`Full Draft/VMAT-TBI_MSc_Thesis_Full_Draft.docx`) against the reference export (`Reference/VMAT-TBI_thesis_references.ris`) and lists what is still unfinished. It uses only the Python standard library (Python 3.8 or newer), works offline and needs no account or API key.

## Run it

From the repository root (PowerShell, Command Prompt or a Linux/macOS shell):

```
python harness/check_thesis.py --out harness/report.md
```

The report is printed on screen and saved to `harness/report.md`. Use `--docx` and `--ris` to point to other files, and `--strict` to make the script exit with an error on any warning.

For a Persian (right-to-left) report, add `--lang fa`:

```
python harness/check_thesis.py --lang fa --out harness/report.fa.md
```

Persian instructions: [README.fa.md](README.fa.md)

## What it checks

| Check | Level |
|---|---|
| A citation such as `(17)` or `(3-5)` points to a reference number that does not exist | error |
| A reference is never cited in the text | warning |
| A reference is first cited out of numeric order | warning |
| Gaps in the reference numbering, or near-identical duplicate entries | warning |
| The reference list in the draft differs from the RIS export (count, or entries missing on either side) | warning |
| Unresolved `[TO BE CONFIRMED]` markers, grouped by section | warning |
| Tables still marked as expected values (`green = expected values`) | warning |

Exit code: `1` if there is an error (or any warning with `--strict`), otherwise `0`.

## Tests

```
python -m unittest discover -s harness/tests -v
```

## Notes

- `report.md` is a snapshot made by the script. Run the script again after editing the thesis to refresh it.
- A numbered list written as "(1) ... (2) ..." inside a sentence looks like a citation and can cause a false positive.
- The `[TO BE CONFIRMED]` and expected-value lists are the to-do list for finishing the thesis: when a value is confirmed or measured, remove the marker and the check count goes down.
