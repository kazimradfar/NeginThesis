# Demo (literature-based) version of the thesis

This folder builds `Full Draft/VMAT-TBI_MSc_Thesis_DEMO_complete.docx`, a
complete version of the thesis draft in which every `[TO BE CONFIRMED]` marker
is resolved and the Results are filled with **demonstration estimates**. Each
estimate is the mean of the results of the published studies cited in the
thesis. The supervisor can use it to judge the expected outcome and the
planning choices before the measurements are made. The original draft is not
changed.

| File | Content |
|---|---|
| `literature_values.csv` | Values taken from the cited studies, with the thesis reference number of each |
| `build_demo.py` | Averages the values, applies them to the planned phantom geometry and writes `demo_values.json` and Figures 4.1–4.9 |
| `make_schematics.py` | Author-drawn schematics. These replace figures that would need copyright permission or photographs, and redraw Figures 3.2 and 3.5 |
| `make_demo_docx.py`, `docxlib.py`, `tense_rules.py` | Write the demo .docx. They copy the EndNote citation fields of the draft, so EndNote keeps working |
| `ASSUMPTIONS.md` | **What to check**: which details came from the proposal and which were assumed |

Rebuild everything (Python 3 with numpy, scipy, matplotlib and python-docx):

```
python demo/build_demo.py
python demo/make_schematics.py
python demo/make_demo_docx.py
python harness/check_thesis.py --docx "Full Draft/VMAT-TBI_MSc_Thesis_DEMO_complete.docx"
```

When real measurements are available:

1. Enter the measured values in `demo_values.json`. Do not rerun `build_demo.py`, because it overwrites this file.
2. Replace the figures in `figures/`, keeping the same file names.
3. Run `python demo/make_demo_docx.py --final`. This writes `Full Draft/VMAT-TBI_MSc_Thesis_complete.docx`, without the demo note and without "demo" in the captions.
4. Run `FINAL=1 node deck_spec.js` in `Presentation/src` to rebuild the slides.
5. Review the interpretive sentences in Chapters 4 and 5, which were written for the demo pattern.

Only Chapter 4 mentions the demo; the Abstract, Discussion and Conclusions take their numbers from the same JSON file.
