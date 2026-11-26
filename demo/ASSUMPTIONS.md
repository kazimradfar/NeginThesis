# Demo version of the thesis: sources and assumptions

`Full Draft/VMAT-TBI_MSc_Thesis_DEMO_complete.docx` is a complete version of the
draft with no `[TO BE CONFIRMED]` markers. The original draft
(`VMAT-TBI_MSc_Thesis_Full_Draft.docx`) is unchanged.

**The results in Chapter 4 are demonstration estimates, not measurements.** Each
value is the mean of the results reported by the studies cited in the thesis
(see `literature_values.csv`). This is stated **only in Chapter 4**: a note at the
start of the chapter, and the captions, which name the studies that were averaged. The
Abstract, Discussion and Conclusions quote the same numbers without a demo label. All of
them are generated from `demo_values.json`, so they change together when real values
are entered (see the Persian README, section on replacing the demo values, and
`python demo/make_demo_docx.py --final`).

Please check the items in section 3 with the supervisor and the department.
They were needed to complete the text, but they did not come from you or from
the proposal.

## 1. Taken from your instructions

| Item | Value used |
|---|---|
| Linear accelerator | Elekta Versa HD (Agility MLC) |
| Treatment planning system | Monaco |
| CT scanner | Philips 64-slice (no model name given in the text) |

## 2. Taken from the approved proposal (`TBI/TBI/proposal of Negina Farhady`)

- Monaco version 5.11.
- Prescription and plan:
  - 12 Gy in 6 fractions, 6 MV.
  - Three isocentres with two arcs each (CW and CCW).
  - Maximum dose rate 250 MU/min.
- Octavius verification with an inclinometer and face-in/face-out composite measurements.
- Film calibration:
  - Geometry: 5 × 5 cm² pieces, 10 PMMA slabs of 1 cm below the film, 10 × 10 cm² field, SAD 100 cm, 200 MU/min.
  - Doses 0–250 cGy in steps of 25 cGy, each irradiated three times.
- Scanning and analysis:
  - Microtek 9800XL scanner in transmission mode, 150 dpi, RGB, TIFF.
  - Analysis in ImageJ with a 1 × 1 cm ROI.
- Phantom: Alderson Rando.
- Team names, and the approval date 1402/09/18 (9 December 2023).
- Ethics: phantom only, "no special ethical considerations".
- Budget: 7 × 40,000,000 Rials for films and 20,000,000 Rials for scanning.
- Timeline in months.

## 3. Assumptions to confirm

| Where | Assumption | Basis |
|---|---|---|
| Title page | Academic year 2025–2026 (1404–1405) | Current year |
| 1.2, 3.x | Rando **male** phantom, 36 slices (0–35), about 90 cm | Standard Rando male; Curto (13) used slices up to 34 |
| 1.2 | "Conformal TBI with lung sparing is not yet available" at the Cancer Institute | Draft text; actual current TBI practice unknown |
| 2.x | "No published Iranian report" (the TBC about the Iranian database search was removed) | Draft text. Iranian databases were **not** searched, because Iranian websites were not to be used |
| Table 3.1 | Octavius phantom with **2D-ARRAY seven29** and VeriSoft | Proposal mentions Octavius and an inclinometer only. It could be Octavius 4D / 1500 |
| Table 3.1 | **PTW 30013 Farmer** chamber with **UNIDOS webline** | Common TRS-398 setup |
| 3.2.5 | Couch: **iBEAM evo** top with the Monaco couch model | Standard Versa HD couch |
| Table 3.2 | CT: 120 kV, 5 mm, 500 mm FOV, standard body kernel, one HFS scan | Typical whole-body settings |
| 3.5.1 | Isocentres at 15.5 / 42.5 / 72.0 cm from the vertex; field lengths 31 / 27 / 36 cm; 2 cm overlaps at 29–31 and 54–56 cm | Geometry chosen to cover 90 cm with 3 fields ≤ 40 cm |
| Table 3.4 | External max-dose cost function 14.4 Gy (120%); junction quadratic overdose 12.6 Gy | Acceptance limits below |
| 3.5.4, Table 3.5 | Normalisation to the mean PTV dose = 12 Gy; D2% ≤ 110%; D98% ≥ 90%; point Dmax ≤ 120% | Curto (13); Kovalchuk (54) D1cc ≈ 121% |
| Table 3.6 | Grid 0.3 cm, statistical uncertainty 1%, 300 control points per arc, minimum segment width 1.0 cm, fluence smoothing medium | Draft values; Curto (13) for the last three |
| 3.6.2 | Calibration depth 5 cm (5 × 1 cm PMMA above the film); reference dose measured with the Farmer chamber in the same slabs | Proposal says "5 layers"; this also resolves the PMMA correction |
| 3.6 | Three scans averaged; 3 × 3 median filter; single red channel (multichannel only as a check); needle marks | Common practice; TG-235 |
| 3.7 | Film levels: slices 5/6, 8/9, 11/12, 13/14, 16/17, 19/20, 21/22, 26/27, 30/31. Additional junction-profile films at 10/11, 12/13, 20/21, 22/23. No CBCT during measurements | Geometry above; Curto (13) |
| 3.x | Tolerances: couch ±1 mm; output action level ±2%; verification film ±3% | Typical departmental values |
| 3.11 | Statistics, film gamma and calibration fit in Python (SciPy) | `demo/build_demo.py` does this |
| Table 3.14 | "7 boxes" of film; linac and CT provided by the Cancer Institute at no cost | Proposal lists no cost for these |
| 3.17 | No ethics committee code is required | Proposal: phantom only |

## 4. How the demo results were obtained

Run `python demo/build_demo.py` and `python demo/make_schematics.py`, then
`python demo/make_demo_docx.py`. All numbers are written to `demo_values.json`.

| Result | Rule (thesis reference numbers) |
|---|---|
| MU, dose rate, beam-on (Table 4.1) | Mean of the two Rando plans of Curto (13): 3,581 MU in total. The MU were distributed over the three fields by the MU per cm of Curto's four fields |
| Planning time | Kumari (30), 4.5–6 h, the only Monaco value found |
| V90%, V95%, D98%, D2% (Table 4.2) | Means of Symons (16), Springer (15) and Curto (13) (phantom and patient plans). D50% was set so that the PTV mean = 12 Gy |
| Body Dmax | Kumari (30): 118% |
| Mean lung dose 8.8 Gy | Mean of seven studies: (13), (16), (17), (32), (46), (71), (72) |
| Lung V12Gy | Uehara (46). V8Gy and V10Gy come from a DVH matched to the mean |
| Gamma, single isocentres | 3%/3 mm: Curto (13) and Symons (16), mean 99.4%. 3%/2 mm: Kovalchuk (54), 98.1% |
| Gamma, junctions | 3%/3 mm: 11 measurements from Curto (13) after the 2 mm correction and Uehara (46), mean 95.6%. 3%/2 mm: Uehara's 3%/2 mm to 3%/3 mm ratio |
| Point doses (Table 4.5) | TPS doses: Curto's Monaco doses at the matching slices. Signs of the film–TPS differences: Curto's central TLD points. Mean absolute difference 1.1% at isocentre levels (mean of (13), (17), (29), (55)) and 3.1% in junctions (mean of (13), (93)) |
| Peripheral and lung points (Bland–Altman) | Curto's TLD differences (13) at the matching locations |
| Lung film vs TPS +1.0% | Mean of Tas (17) and Yaray (55) |
| Lung dose per plane | Simple dose model scaled to the mean lung dose of 8.8 Gy |
| 2D film gamma per plane | Calculated on demo film maps: 1 mm registration shift, about 1% pixel noise after filtering, and lung variations matching the spread of Curto's lung TLDs |
| Calibration (Table 4.4) | Simulated EBT3 red-channel response of typical size (37), (96), fitted with the Devic function |
| Uncertainty budget | TRS-398 (88) reference dose 1.5%; other components typical of TG-235 (36) |

## 5. Figures

- Chapter 4 figures (4.1–4.9) are drawn from the demo values.
- Literature figures that would have needed copyright permission (2.4, 2.6, 2.7, 2.10, 2.11, 2.12) were replaced by original schematics. Each caption says "drawn by the author after ...". The photo slots (2.8, 3.4) and the Monaco screenshot (3.3) were also replaced by schematics.
- Figures 3.2 and 3.5 were redrawn for the final film plan and calibration depth.
- When real photographs and measurements exist, replace these figures.

## 6. After opening in Word

Right-click the Table of Contents and choose **Update Field**, then update the
entire table, so that the new Abstract appears. The citations are the original
EndNote fields. "Update Citations and Bibliography" in EndNote still works.
