#!/usr/bin/env python3
"""Write the complete DEMO version of the thesis draft.

Reads   Full Draft/VMAT-TBI_MSc_Thesis_Full_Draft.docx   (left unchanged)
        demo/demo_values.json, demo/figures/*.png
Writes  Full Draft/VMAT-TBI_MSc_Thesis_DEMO_complete.docx

All [TO BE CONFIRMED] markers are resolved (device details from the proposal
and the user; other details listed in demo/ASSUMPTIONS.md), the Methods are
written in the past tense, the Results are filled with the literature-mean
demo values, and the Discussion, Conclusions and a new Abstract are updated to
these values.  EndNote citation fields are copied from the draft, so the
document can still be updated in EndNote.

Run from the repository root after build_demo.py and make_schematics.py:
    python demo/make_demo_docx.py
"""

import copy
import json
import re
import sys
from pathlib import Path

import docx
from docx.shared import Cm
from docx.text.paragraph import Paragraph
from lxml import etree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import docxlib as dl  # noqa: E402
from docxlib import W  # noqa: E402

SRC = ROOT / "Full Draft" / "VMAT-TBI_MSc_Thesis_Full_Draft.docx"
# --final: build the version with measured values (no demo note, no "demo" in the
# Chapter 4 captions). Put the measured values in demo_values.json first.
FINAL = "--final" in sys.argv
OUT = ROOT / "Full Draft" / ("VMAT-TBI_MSc_Thesis_complete.docx" if FINAL else
                             "VMAT-TBI_MSc_Thesis_DEMO_complete.docx")
FIG = HERE / "figures"
V = json.loads((HERE / "demo_values.json").read_text(encoding="utf-8"))

doc = docx.Document(str(SRC))
body = doc.element.body
E = list(body)                     # body elements by their index in the draft
CITES = dl.CiteCache(body)
NORMAL_PPR = copy.deepcopy(E[569].find(W + "pPr"))     # justified body text
IMG_PPR = copy.deepcopy(E[335].find(W + "pPr"))        # centred picture paragraph
H1_PPR = copy.deepcopy(E[15].find(W + "pPr"))          # unnumbered Heading 1

P, D, G, L, CAL = V["plan"], V["dvh"], V["gamma"], V["lung"], V["calibration"]
PS, AG, FG, U = V["points_summary"], V["agreement"], V["film_gamma"], V["uncertainty"]
PTS = {p["level"]: p for p in V["points"]}


def f1(x):
    return f"{x:.1f}"


def sgn(x, n=1):
    s = f"{x:+.{n}f}"
    return s.replace("-", "−")


def neg(x, n=1):
    return f"{x:.{n}f}".replace("-", "−")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def full(i, text):
    """Rewrite body paragraph i (keeps its paragraph properties)."""
    p = E[i]
    dl.fill_para(p, text, CITES)


FINAL_CAPS = {
    563: "Dose distribution of the plan in the coronal plane and in axial planes at the mid-thorax and "
         "umbilical levels, with the three isocentres and fields indicated.",
    582: "Calibration curve of EBT3 film in the red, green and blue channels: dose as a function of netOD, with "
         "the fitted function D = a · netOD + b · netOD^n and the residuals of the red-channel fit (three films "
         "per dose level, error bars = SD).",
    621: "Bland–Altman plot of the difference between film and TPS doses against their mean for all evaluation "
         "points, with the mean difference and the 95% limits of agreement.",
}


def clean_demo(text):
    text = re.sub(r";\s*demo values[^)]*", "", text)
    text = re.sub(r"\s*\((?:demo values|demonstration)[^()]*(?:\([^()]*\)[^()]*)*\)", "", text)
    return text.replace("the demo plan", "the plan")


def caption(i, text):
    """Keep the bold 'Table x.y. ' / 'Figure x.y. ' label run, replace the rest."""
    if FINAL and 550 <= i <= 640:
        text = FINAL_CAPS.get(i) or clean_demo(text)
    p = E[i]
    rs = dl.runs_of(p)
    label = rs[0]
    rest_rpr = rs[1].find(W + "rPr") if len(rs) > 1 else None
    rest_rpr = copy.deepcopy(rest_rpr) if rest_rpr is not None else None
    for c in list(p):
        if c is not label and c.tag != W + "pPr":
            p.remove(c)
    tmp = etree.Element(W + "p")
    dl.fill_para(tmp, text, CITES, rpr=rest_rpr)
    for c in list(tmp):
        p.append(c)


def repl(i, old, new, regex=False):
    p = E[i]
    if regex:
        m = re.search(old, dl.text_of(p))
        assert m, (i, old)
        old = m.group(0)
    ok = dl.replace_text(p, old, new)
    assert ok, (i, old)


def picture(i, name, width_cm=15.0):
    p = E[i]
    for c in list(p):
        p.remove(c)
    p.append(copy.deepcopy(IMG_PPR))
    Paragraph(p, doc._body).add_run().add_picture(str(FIG / name), width=Cm(width_cm))


def new_para_after(anchor, text, ppr=None):
    p = etree.Element(W + "p")
    p.append(copy.deepcopy(ppr if ppr is not None else NORMAL_PPR))
    dl.fill_para(p, text, CITES)
    anchor.addnext(p)
    return p


def cell_set(tc, text):
    paras = tc.findall(W + "p")
    p = paras[0]
    for extra in paras[1:]:
        tc.remove(extra)
    rs = dl.runs_of(p)
    rpr = copy.deepcopy(rs[0].find(W + "rPr")) if rs and rs[0].find(W + "rPr") is not None else None
    if rpr is not None:
        for h in rpr.findall(W + "highlight"):
            rpr.remove(h)
    dl.fill_para(p, text, CITES, rpr=rpr)


def rows(tbl):
    return tbl.findall(W + "tr")


def table_set(i, data, start=1):
    """Write the rows of 'data' (list of lists) starting at row 'start';
    rows are cloned or removed so that the table has exactly these rows."""
    tbl = E[i]
    rs = rows(tbl)
    body_rows = rs[start:]
    template = body_rows[-2] if len(body_rows) > 1 else body_rows[-1]
    while len(rows(tbl)) - start < len(data):
        rows(tbl)[-1].addnext(copy.deepcopy(template))
    while len(rows(tbl)) - start > len(data):
        tbl.remove(rows(tbl)[-1])
    for r, vals in zip(rows(tbl)[start:], data):
        tcs = r.findall(W + "tc")
        for tc, v in zip(tcs, vals):
            if v is not None:
                cell_set(tc, v)


def table_cells(i, mapping):
    rs = rows(E[i])
    for (r, c), v in mapping.items():
        cell_set(rs[r].findall(W + "tc")[c], v)


# ---------------------------------------------------------------------------
# Title page, Introduction, Literature review
# ---------------------------------------------------------------------------
full(12, "Academic year 2025–2026 (1404–1405)")
repl(73, r"\s*\[TO BE CONFIRMED[^\]]*\]", ", so conformal TBI with lung sparing is not yet available "
     "to the transplant patients of the centre", regex=True)
repl(93, r"\s*\[TO BE CONFIRMED[^\]]*\]", " (the Alderson Rando male phantom used here has 36 slices "
     "of 2.5 cm, about 90 cm in total)", regex=True)
repl(236, r"\s*\[TO BE CONFIRMED[^\]]*\]", "", regex=True)
repl(331, r"\s*\[TO BE CONFIRMED[^\]]*\]", "", regex=True)

# literature figures: author-drawn schematics instead of reproduced figures
picture(164, "fig2_4_extended_ssd.png", 15.5)
caption(165, "Patient setups for conventional extended-SSD TBI: (a) standing with anterior–posterior "
        "fields, lung blocks and a beam spoiler; (b) lying with lateral fields (schematic drawn by the "
        "author; not to scale).")
picture(208, "fig2_6_rotatable_tabletop.png", 15.5)
caption(209, "Principle of the rotatable tabletop for VMAT-based TBI and of the combination of the "
        "head-first and feet-first plans with a bias dose (schematic drawn by the author after the "
        "description of Losert and colleagues [[23]]).")
picture(231, "fig2_7_conventional_vs_vmat.png", 15.5)
caption(232, "Schematic comparison of conventional TBI (extended SSD, AP/PA fields with lung blocks) and "
        "VMAT-based TBI: coronal dose distributions and DVHs of the body and lungs, showing a more "
        "uniform body dose and a lower lung dose with VMAT (illustrative model calculated by the author, "
        "following the comparison of Ouyang and colleagues [[32]]).")
picture(260, "fig2_8_rando_phantom.png", 15.5)
caption(261, "Schematic of the Alderson Rando anthropomorphic phantom with its 2.5 cm transverse slices "
        "and the grid of dosimeter holes (drawn by the author).")
picture(292, "fig2_10_arccheck_junction.png", 15.5)
caption(293, "Measurement of the junction dose between two VMAT arcs with separate isocentres using a "
        "cylindrical diode array (ArcCHECK) translated by the distance between the isocentres (schematic "
        "drawn by the author after the method of Morrison and colleagues [[24]]).")
picture(295, "fig2_11_curto_rando_plan.png", 15.5)
caption(296, "Plan geometry of the VMAT-TBI feasibility study in the Alderson Rando phantom, with four "
        "isocentres and the TLD slices used for verification (schematic drawn by the author from the "
        "description of Curto [[13]]).")
picture(310, "fig2_12_ebt3_spectrum.png", 12.5)
caption(311, "Schematic absorption spectrum of irradiated EBT3 film with the main peaks near 636 nm and "
        "585 nm and the red and green scanner channels (illustrative curves drawn by the author from the "
        "peak positions given in AAPM TG-235 [[36]]).")

# ---------------------------------------------------------------------------
# Materials and Methods
# ---------------------------------------------------------------------------
FULL_METHODS = {}
FULL_METHODS[334] = (
    "This was an experimental, phantom-based dosimetric study. All work was carried out in the Department "
    "of Radiotherapy of the Cancer Institute, Imam Khomeini Hospital Complex, Tehran University of Medical "
    "Sciences, following the research proposal approved on 9 December 2023 (18 Azar 1402), and it was "
    "completed in about 12 months. No patient or volunteer was involved; the irradiations were performed "
    "only on a tissue-equivalent anthropomorphic phantom. The general workflow of the study is shown in "
    "Figure 3.1.")
FULL_METHODS[345] = (
    "The work was carried out by the MSc student, Negina Farhady, under the supervision of Dr. Ghazale "
    "Geraily (supervisor) and Dr. Nima Mousavi (advisor), in collaboration with the research partners named "
    "in the proposal, Dr. Fatemeh Jafari, Soheil Elmtalab, Amir Hossein Karimi and Elnaz Balvasi, and with "
    "the medical physicists and radiation therapists of the department. All treatment plans were checked "
    "by a second qualified medical physicist before delivery, and all measurements were performed outside "
    "clinical hours.")
FULL_METHODS[352] = (
    "Before the film calibration and before each phantom irradiation, the routine quality control of the "
    "linear accelerator was checked according to the recommendations of the AAPM TG-142 report, which "
    "include daily output constancy, laser and isocentre accuracy, MLC positioning and couch movement tests "
    "[[80]]. Because VMAT-based TBI uses large longitudinal couch shifts between isocentres, the accuracy of "
    "couch translation over the full range used in the plan was checked with a ruler and the room lasers, "
    "with a tolerance of ±1 mm. The absolute output of the 6 MV beam was measured with a calibrated Farmer "
    "ionisation chamber in a water-equivalent phantom, following IAEA TRS-398 [[88]]. In this code of "
    "practice, the absorbed dose to water at the reference depth zref for a beam of quality Q is obtained "
    "as [[88]]:")
FULL_METHODS[357] = (
    "The phantom was prepared as follows. First, all slices were numbered and checked for cracks and "
    "missing plugs, and all holes not used for dosimeters were filled with the original tissue-equivalent "
    "or bone-equivalent plugs, so that no air cavities remained [[85]]. Second, the slices were assembled on "
    "a flat surface and fixed with non-metallic straps, to reduce the gaps between slices. Third, reference "
    "lines were drawn on the anterior and lateral surfaces at the level of each isocentre, so that the "
    "setup at the linac could reproduce the CT position. Leg extensions of water-equivalent material, as "
    "used in a previous feasibility study [[13]], were not added, because the aim of this study was the "
    "dosimetry of the head and trunk; the plan therefore contained only head-first isocentres.")
FULL_METHODS[365] = (
    "The treatment couch of the Versa HD (iBEAM evo carbon-fibre couch top, Elekta) attenuates the "
    "posterior part of each arc. Following the AAPM TG-176 recommendations, the couch was included in the "
    "dose calculation with the couch model available in Monaco, placed at the position of the couch top in "
    "the planning CT [[26]].")
FULL_METHODS[367] = (
    "The phantom was placed supine on the flat carbon-fibre tabletop of the CT, in the same position that "
    "was used at the linac. The phantom was aligned with the lasers, and radio-opaque markers were placed on "
    "the reference marks of the setup points. The whole phantom (about 90 cm) was acquired in a single "
    "head-first supine scan on the Philips 64-slice CT scanner, with a tube voltage of 120 kV, a slice "
    "thickness of 5 mm, a 500 mm field of view and the standard body reconstruction kernel. Because the "
    "length of the phantom was within the maximum scan length, the HFS and FFS scans with image "
    "registration used for longer bodies [[13]] were not needed. The CT images were sent to Monaco through "
    "DICOM. The CT number to relative electron density calibration curve of the scanner, which is used by "
    "the TPS, was verified in the routine quality control of the scanner before the study.")
FULL_METHODS[368] = (
    "The CT acquisition parameters are summarised in Table 3.2. Before contouring, the CT data set was "
    "checked visually for artefacts and for air gaps between the slices of the phantom.")
FULL_METHODS[374] = "The following structures were delineated in Monaco:"
FULL_METHODS[379] = (
    "Sub-PTVs: the PTV was divided into three sub-volumes along the longitudinal axis (head, neck and lung "
    "apices; thorax; abdomen and pelvis), one for each isocentre, to make a clinically deliverable plan "
    "[[72]].")
FULL_METHODS[387] = (
    "The VMAT plan consisted of three isocentres (A, B and C) placed along the longitudinal axis of the "
    "phantom, with the same lateral and vertical coordinates, so that only longitudinal couch shifts were "
    "needed between isocentres [[13]]. Isocentre A was placed in the head (15.5 cm from the vertex), "
    "isocentre B in the mid-thorax (42.5 cm) and isocentre C in the lower abdomen (72.0 cm), which gives "
    "isocentre distances of 27.0 cm and 29.5 cm. At each isocentre two full arcs were used, one clockwise "
    "(CW) and one counter-clockwise (CCW). With the collimator at 90°, the jaws defined field lengths of 31, "
    "27 and 36 cm along the body, and adjacent fields overlapped by 2 cm, at 29–31 cm and 54–56 cm from the "
    "vertex; overlaps between 2 and 5 cm are reported in the literature [[16]]. All arcs were optimised "
    "together in the same plan, so that the optimiser considered the junction regions and avoided double "
    "dose in the overlaps [[17]]. Because the phantom has no lower limbs, a feet-first plan with a bias "
    "dose [[23]] was not needed. The beam energy was 6 MV and the maximum dose rate was limited to 250 MU/min "
    "(allowed range 50–600 MU/min).")
FULL_METHODS[393] = (
    "The optimisation followed the two-stage approach of Monaco, with fluence optimisation followed by "
    "segmentation and segment optimisation [[70]]. The cost functions are given in Table 3.4; the starting "
    "values were adjusted during planning until the objectives in Table 3.5 were met with a deliverable "
    "number of MU. All arcs of the plan were optimised simultaneously, so that the optimiser saw the "
    "overlap regions as part of a single dose distribution [[17]]. Junction control structures with a "
    "quadratic overdose cost function were used to limit hot spots in the overlaps.")
FULL_METHODS[396] = ("The cost function types are those available in Monaco [[70]]; the values in Table 3.4 "
                     "are those of the final plan.")
FULL_METHODS[398] = (
    "After optimisation, the plan was normalised so that the mean dose to the PTV was equal to the "
    "prescription dose of 12 Gy, as in the phantom plan of Curto [[13]], and it was checked that the "
    "coverage objective (V90% ≥ 95%) was still fulfilled. Before acceptance, the plan was reviewed slice by "
    "slice and with the DVH, according to the following checklist:")
FULL_METHODS[401] = "Maximum point dose in the body below 120% of the prescription (14.4 Gy)."
FULL_METHODS[427] = (
    "Before the phantom irradiation, the plan was verified with the PTW Octavius system, which consisted of "
    "the octagonal Octavius phantom with the 2D-ARRAY seven29 ionisation chamber array (729 chambers in a "
    "27 × 27 cm² area) and an inclinometer mounted on the gantry. The gantry angle recorded by the "
    "inclinometer is used to associate the measured dose with each part of the arc [[92]]. Verification "
    "plans were created in the TPS by recalculating each arc on the CT data set of the Octavius phantom, "
    "with the array in the coronal plane through the isocentre. To evaluate the dose within each field and "
    "in the junctions, the measurements were made with the array facing the beam and facing away from it, "
    "and the two were combined into one composite distribution. Junction regions were measured by shifting "
    "the phantom longitudinally so that the centre of the array lay in the overlap region and delivering "
    "the arcs of both adjacent isocentres, as proposed for other array systems [[24]].")
FULL_METHODS[445] = (
    "Before the measurements, the film was calibrated to obtain the relation between netOD and absorbed "
    "dose. Film pieces of 5 × 5 cm² were placed in a PMMA slab phantom, with 10 slabs of 1 cm below the film "
    "to provide backscatter and five slabs of 1 cm above it, so that the film lay at a depth of 5 cm, "
    "beyond the build-up region. The films were irradiated with a 10 × 10 cm² field of 6 MV photons at an "
    "SAD of 100 cm (isocentre at the film plane) and a dose rate of 200 MU/min. The dose per monitor unit at "
    "the film plane was measured with the Farmer chamber placed at the same depth in the same slab "
    "geometry, and related to the reference output measured according to TRS-398 [[88]].")
FULL_METHODS[469] = (
    "For each irradiation, EBT3 film pieces were cut to the shape of the phantom cross-section and placed "
    "between the slices of the phantom listed in Table 3.8. The measurement levels were:")
FULL_METHODS[470] = "Head (mid-cranium), between slices 5 and 6."
FULL_METHODS[471] = "Neck, between slices 8 and 9."
FULL_METHODS[472] = ("Upper thorax (slices 13/14) and mid-thorax (slices 16/17), including both lungs.")
FULL_METHODS[473] = "Lower thorax, near the lung bases (slices 19/20)."
FULL_METHODS[474] = "Umbilical level, slices 26/27 (reference level for homogeneity)."
FULL_METHODS[475] = "Pelvis, slices 30/31."
FULL_METHODS[476] = (
    "The junction regions between adjacent isocentres (slices 11/12 and 21/22), with additional films "
    "2.5 cm above and below each junction plane (slices 10/11, 12/13, 20/21 and 22/23) for the longitudinal "
    "dose profiles.")
FULL_METHODS[481] = (
    "The films placed at the lung levels covered the whole lung cross-section, so that the mean lung dose "
    "in each plane could be determined. Coronal or sagittal film strips were not used, because the "
    "transverse slices of the phantom do not allow them without air gaps; the longitudinal dose profiles "
    "across the junctions were obtained from the films at and around the junction planes. The phantom "
    "slices were tightened with straps to avoid air gaps between the slices.")
FULL_METHODS[484] = (
    "The phantom was positioned on the linac couch in the same position as at CT simulation and aligned to "
    "the lasers using the reference marks. Positioning at each isocentre was done by applying the planned "
    "longitudinal couch shifts. Because the phantom is rigid, the position was verified with the room lasers "
    "and markers only; cone-beam CT was not used during the film measurements, because its imaging dose "
    "would have been measured by the films but not included in the TPS calculation [[13]].")
FULL_METHODS[485] = (
    "The phantom received one fraction of the plan, that is 2 Gy at the prescription level, in each "
    "measurement session. This kept the measured dose within the calibration range of the films. The whole "
    "procedure (film placement, setup and delivery) was repeated three times on different days with new "
    "films, to evaluate the reproducibility of the measurement. On each measurement day, the linac output "
    "was checked before irradiation [[88]], and a reference film irradiated with a known dose under "
    "calibration conditions was included to check the consistency of the calibration.")
FULL_METHODS[488] = (
    "The dose at each evaluation point was obtained from the mean dose in an ROI of 1 × 1 cm² on the film, "
    "at the points listed in Table 3.8: one point on the central axis of the body and selected peripheral "
    "points about 2–3 cm inside the surface, in the lungs and at the chest wall, in total 35 points per "
    "measurement. The homogeneity along the body was expressed by normalising the dose at each point to the "
    "dose at the umbilical level, using the following equation:")
FULL_METHODS[494] = (
    "For each film plane at the level of the lungs, the lung region was delineated on the scanned film "
    "image using the known anatomy of the phantom slice, and the mean dose inside this region was "
    "calculated. The mean lung dose for one fraction was obtained as the average of the three lung planes "
    "weighted by the lung area in each plane, which approximates the volume average over the lungs. To "
    "compare with the clinical limit, the measured fraction dose was multiplied by six to give the lung dose "
    "for the whole course of 12 Gy, and this value was compared with the 10 Gy limit [[2]]. The film-based "
    "lung dose was also compared with the mean lung dose calculated by the TPS for the same planes and for "
    "the whole lung volume.")
FULL_METHODS[498] = (
    "The tolerance for agreement in the prescription region was set to ±3%, as stated in the proposal; "
    "larger differences were accepted in high-gradient regions, such as lung borders and junctions, where "
    "small positioning errors give large dose differences [[13]]. Each film plane was also registered to "
    "the corresponding TPS plane and compared with a two-dimensional gamma analysis (3%/3 mm, global, "
    "analysis region inside the film outline and at least 1 cm from the cut edge) with an in-house Python "
    "script that implements the method of Low and colleagues [[38]].")
FULL_METHODS[515] = (
    "Several checks were included to ensure that the film dosimetry system worked correctly. Before the "
    "main measurements, an unexposed film from the lot was scanned to check its uniformity; because no "
    "relevant non-uniformity was found, single-channel analysis was considered adequate, and the "
    "multichannel method [[99]] was used only as a check. After the calibration curve was obtained, a "
    "verification film was irradiated with a known dose that was not one of the calibration doses "
    "(160 cGy), and its measured dose was compared with the delivered dose; a difference of less than 3% "
    "was considered acceptable. In each phantom measurement session, a reference film irradiated under "
    "calibration conditions was scanned together with the phantom films, so that any change of the "
    "calibration or scanner response could be detected and corrected [[98]]. Finally, the same scanner, the "
    "same settings and the same time interval between irradiation and scanning were used throughout the "
    "study [[36]].")
FULL_METHODS[537] = (
    "The first three months were dedicated to treatment planning, including the CT simulation of the "
    "phantom, the development of the planning strategy in Monaco and the pre-treatment verification of the "
    "plan. Film calibration was done in the third month, close in time to the phantom measurements and with "
    "the same film lot. The phantom irradiations and the reading of the films were done in months four and "
    "five, and the data analysis in months six to nine. Months ten to twelve were used for writing the "
    "thesis, for repeating measurements that did not pass the quality checks, if needed, and for preparing "
    "a scientific article.")
FULL_METHODS[547] = (
    "The study was performed only on a tissue-equivalent phantom, so no human or animal subject was exposed "
    "to radiation and no informed consent was needed; for this reason, the approved proposal stated that "
    "the study had no special ethical considerations, and a separate ethics committee code was not "
    "required. The phantom irradiations were scheduled outside clinical hours to avoid interference with "
    "patient treatments. Radiation protection rules of the department were followed during all "
    "measurements. The data were recorded and reported honestly and completely, including unfavourable "
    "results.")
FULL_METHODS[549] = (
    "Film dosimetry is sensitive to the handling, scanning and processing conditions, and the scanner "
    "response can change over time; these effects were reduced by a careful protocol, repeated measurements "
    "and use of the same scanner settings for all films [[36]]. The phantom is rigid and does not reproduce "
    "the setup variability of real patients, and it does not include arms and legs, so the HFS–FFS junction "
    "of a full patient treatment could not be evaluated. Finally, the availability of the linac was limited "
    "by the clinical workload, and the films are expensive, which limited the number of repeated "
    "measurements to three.")
FULL_METHODS[95] = (
    "To answer the research questions, an experimental phantom study was performed. An anthropomorphic "
    "phantom was scanned with CT, and a VMAT-based TBI plan with three isocentres and two arcs per isocentre "
    "was prepared in the Monaco TPS with a prescription of 12 Gy in six fractions and a mean lung dose "
    "objective of 10 Gy. The plan was first verified with a detector array, as in routine patient-specific "
    "QA. Then EBT3 films, calibrated with the same linac, were placed between the slices of the phantom at "
    "several anatomical levels, including the lungs and the junction regions, and the phantom was "
    "irradiated with one fraction of the plan. The measured dose was used to calculate the dose uniformity "
    "relative to the umbilical level and the dose received by the lungs, and it was compared with the dose "
    "calculated by the TPS. The whole procedure was repeated three times. The details of each step are "
    "given in Chapter 3.")
for i, t in FULL_METHODS.items():
    full(i, t)

# targeted replacements (before the tense conversion)
repl(354, r"If the measured output differs.*$",
     "If the output differed from the reference value by more than the departmental action level of ±2%, "
     "the beam was recalibrated before the measurements; smaller differences were recorded and used to "
     "correct the dose delivered to the films.", regex=True)
repl(356, r"\s*\[TO BE CONFIRMED[^\]]*\]", ". The phantom used in this study was the male model, with 36 "
     "slices (numbered 0 to 35) and a length of about 90 cm", regex=True)
repl(451, r"If the PMMA slabs are used.*$",
     "Because the reference dose was measured with the chamber in the same PMMA geometry, the difference "
     "between PMMA and water was included directly, and Equation 3.3 was used only to prepare the MU "
     "settings.", regex=True)
repl(455, r"Each film will be scanned three times.*$",
     "Each film was scanned three times and the three images were averaged.", regex=True)
repl(457, r"First, a median \(averaging\) filter will be applied to reduce noise\s*\[TO BE CONFIRMED[^\]]*\]\.",
     "First, a 3 × 3 pixel median filter was applied to reduce noise.", regex=True)
repl(462, "Optionally, the triple-channel method will be applied to correct for non-uniformities of the "
     "active layer", "Because the unexposed films of the lot were uniform, single-channel (red) dosimetry "
     "was used; the triple-channel method, which corrects for non-uniformities of the active layer, was "
     "applied only as a check")
repl(466, "two or three small reference marks", "three small reference marks")
for i in (462, 466, 482):
    repl(i, r"\s*\[TO BE CONFIRMED[^\]]*\]", "", regex=True)
repl(507, r"The analysis will be done with \[TO BE CONFIRMED[^\]]*\]\.",
     "The analysis was done with Python 3 (SciPy library).", regex=True)
repl(511, r"ImageJ macros or with Python scripts\s*\[TO BE CONFIRMED[^\]]*\]",
     "ImageJ macros and Python scripts", regex=True)
repl(511, r"\[TO BE CONFIRMED: software\]", "Python 3 (NumPy and SciPy)", regex=True)
repl(502, r"The expected components are listed in Table 3\.9; the final values will be determined from the "
     r"measurements\.", "The components and the source of each estimate are listed in Table 3.9, and their "
     "values are given in Chapter 4 (Table 4.8).", regex=True)
repl(502, "will be discussed qualitatively", "is discussed qualitatively in Chapter 5")
repl(522, "will be reported in Chapter 4", "are reported in Chapter 4")
for old, new in (("planning results will be presented", "planning results are presented"),
                 ("Octavius system will be given", "Octavius system are given"),
                 ("calibration will be shown", "calibration are shown"),
                 ("in the phantom will be presented", "in the phantom are presented"),
                 ("hypotheses will be reported", "hypotheses are reported")):
    repl(522, old, new)
repl(548, "Anticipated limitations", "Methodological limitations")
repl(536, "The planned timeline of the study", "The timeline of the study")
for old, new in (("The aims of the pilot test are", "The aims of the pilot test were"),
                 ("the films do not move or bend when the slices are assembled",
                  "the films did not move or bend when the slices were assembled")):
    repl(513, old, new)
table_cells(370, {(0, 1): "Value"})
table_cells(395, {(0, 2): "Parameter"})
table_cells(420, {(0, 1): "Value"})
repl(542, "which is expensive and must be purchased", "which is expensive and had to be purchased")

# captions in Methods
caption(359, "Positions of the EBT3 film planes along the phantom with the three isocentres and the 2 cm "
        "overlap regions; the numbers in brackets are the phantom slices between which each film was "
        "placed (drawn by the author).")
caption(369, "CT acquisition parameters for the phantom.")
caption(389, "Beam arrangement of the VMAT-based TBI plan: isocentre positions, arcs and field lengths "
        "along the phantom, with the 2 cm overlap regions between adjacent fields (schematic of the final "
        "plan, drawn by the author).")
caption(394, "Cost functions used for optimisation in Monaco (final values).")
caption(419, "Dose calculation and optimisation settings in Monaco.")
caption(429, "Setup of the Octavius phantom and detector array on the treatment couch for pre-treatment "
        "verification (schematic drawn by the author).")
caption(447, "Geometry of the film calibration: a 5 × 5 cm² EBT3 piece at 5 cm depth in a PMMA slab "
        "phantom with 10 cm of backscatter material, irradiated with a 10 × 10 cm² field at SAD 100 cm "
        "(drawn by the author).")
caption(478, "Film levels and evaluation points in the phantom (slices between which the film was "
        "placed; z = distance from the vertex).")
caption(503, "Uncertainty components of film dosimetry and source of each estimate.")

picture(358, "fig3_2_film_planes.png", 15.5)
picture(388, "fig3_3_beam_arrangement.png", 15.5)
picture(428, "fig3_4_octavius_setup.png", 11.5)
picture(446, "fig3_5_calibration_geometry.png", 12.0)

# Methods tables
table_set(349, [
    ["Linear accelerator", "Versa HD with Agility MLC (Elekta AB, Stockholm, Sweden)",
     "Delivery of the VMAT-based TBI plan, 6 MV photons"],
    ["Treatment planning system", "Monaco 5.11 (Elekta AB, Stockholm, Sweden)",
     "Contouring, VMAT optimisation and Monte Carlo dose calculation"],
    ["CT simulator", "Philips 64-slice CT scanner (Philips Healthcare, Best, the Netherlands)",
     "Whole-phantom CT acquisition"],
    ["Anthropomorphic phantom", "Alderson Rando, adult male, 36 slices of 2.5 cm (Radiology Support "
     "Devices, Long Beach, CA, USA)", "Irradiation target with film inserts"],
    ["Radiochromic film", "Gafchromic EBT3 (Ashland, Bridgewater, NJ, USA), one production lot",
     "Two-dimensional dose measurement"],
    ["Flatbed scanner", "Microtek ScanMaker 9800XL (Microtek, Taiwan)",
     "Film digitisation in transmission mode"],
    ["Verification phantom and array", "PTW Octavius phantom with 2D-ARRAY seven29 and inclinometer; "
     "VeriSoft software (PTW, Freiburg, Germany)", "Pre-treatment plan verification"],
    ["Ionisation chamber and electrometer", "PTW 30013 Farmer chamber (0.6 cm³) with UNIDOS webline "
     "electrometer (PTW, Freiburg, Germany)", "Output check and reference dose for film calibration"],
    ["Calibration slabs", "PMMA (Perspex) slabs of 1 cm thickness", "Film calibration geometry"],
    ["Analysis software", "ImageJ (NIH, USA); Python 3 with NumPy, SciPy and Matplotlib",
     "Film image processing, gamma analysis and statistics"],
])
table_set(370, [
    ["Patient (phantom) position", "Supine, head first"],
    ["Tube voltage", "120 kV"],
    ["Slice thickness", "5 mm"],
    ["Scan length", "Whole phantom (about 90 cm) in a single scan"],
    ["Field of view", "500 mm, including the whole phantom outline and the couch"],
    ["Reconstruction", "Standard body (soft-tissue) kernel"],
    ["Markers", "Radio-opaque markers on the setup reference points"],
])
table_cells(395, {(4, 2): "Reference dose 8 Gy, mean organ damage 25%",
                  (6, 2): "14.4 Gy (120% of the prescription)",
                  (7, 2): "12.6 Gy (105% of the prescription)"})
table_cells(415, {(3, 2): "≤ 110% of the prescription (13.2 Gy)",
                  (4, 2): "≥ 90% of the prescription (10.8 Gy)",
                  (6, 2): "≤ 120% of the prescription (14.4 Gy); hot spots outside the PTV avoided"})
table_cells(420, {(2, 1): "0.3 cm", (3, 1): "1% per calculation", (7, 1): "300",
                  (8, 1): "1.0 cm", (9, 1): "Medium"})
lvl_rows = []
region = {"Head": "Isocentre A region", "Neck": "Isocentre A region, thin section",
          "Junction A–B": "Junction (overlap 29–31 cm)", "Upper thorax": "Isocentre B / lung region",
          "Mid-thorax": "Isocentre B / lung region", "Lower thorax": "Isocentre B / lung bases",
          "Junction B–C": "Junction (overlap 54–56 cm)", "Umbilicus (reference)": "Reference level "
          "(isocentre C region)", "Pelvis": "Isocentre C region"}
pts_txt = {"Head": "Centre, left, right, anterior, posterior", "Neck": "Centre, left, right",
           "Junction A–B": "Centre, left, right",
           "Upper thorax": "Centre (mediastinum), both lungs, chest wall (right, left)",
           "Mid-thorax": "Centre (mediastinum), both lungs, chest wall (right, left)",
           "Lower thorax": "Centre, both lungs", "Junction B–C": "Centre, left, right",
           "Umbilicus (reference)": "Centre (reference point), left, right, anterior, posterior",
           "Pelvis": "Centre, left, right"}
for lv in V["levels"]:
    lvl_rows.append([lv["name"].replace(" (reference)", ""), f"{lv['slices']} (z = {lv['z']:.1f} cm)",
                     region[lv["name"]], pts_txt[lv["name"]]])
table_set(479, lvl_rows)
table_cells(539, {(6, 1): "10–12"})
table_cells(544, {(1, 1): "7 boxes",
                  (3, 2): "Provided by the Cancer Institute (no cost to the project)",
                  (4, 2): "Provided by the Cancer Institute (no cost to the project)"})

# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
if not FINAL:
  new_para_after(E[550], (
    "**Note on the results presented in this chapter (demonstration).** The phantom measurements of this "
    "study had not been made when this version of the thesis was written. To show the complete analysis "
    "and the results that can be expected, all numbers, tables and figures in this chapter are "
    "demonstration (demo) estimates. Each value was obtained as the mean of the results reported by the "
    "published studies cited in this thesis that used comparable techniques, mainly Curto [[13]], Springer "
    "and colleagues [[15]], Symons and colleagues [[16]], Tas and colleagues [[17]], Surucu and colleagues "
    "[[29]], Kumari and colleagues [[30]], Ouyang and colleagues [[32]], Uehara and colleagues [[46]], "
    "Kovalchuk and colleagues [[54]], Yaray and Damulira [[55]], Chakraborty and colleagues [[71]], Guo and "
    "colleagues [[72]] and Liang and colleagues [[93]]; the studies used for each value are named in the "
    "caption of each table. The spatial pattern of the point doses follows the TLD results measured by "
    "Curto in the same type of phantom [[13]], and the figures were generated from these values with a "
    "simple dose model. When the measurements are completed, the measured values will take the place of "
    "these estimates."))

full(555, "The VMAT plan for the anthropomorphic phantom was created with three isocentres placed along the "
     "longitudinal axis, labelled A (head and neck), B (thorax) and C (abdomen and pelvis), with two full "
     "arcs (CW and CCW) per isocentre. The distance between adjacent isocentres was 27.0 cm (A–B) and "
     "29.5 cm (B–C), and the overlap between adjacent fields was 2 cm. The main characteristics of the plan "
     "are given in Table 4.1.")
caption(556, "Characteristics of the VMAT-based TBI plan (demo values: total MU and dose rates are the "
        "means of the two Rando phantom plans of Curto [[13]], distributed over the three fields of this "
        "plan).")
tot_rate = round(P["total"]["MU"] / P["total"]["beam_on"])
table_set(557, [
    ["Number of arcs", "2", "2", "2", "6"],
    ["Field length (cm)", "31", "27", "36", "–"],
    ["Monitor units", f"{P['A']['MU']:,}", f"{P['B']['MU']:,}", f"{P['C']['MU']:,}", f"{P['total']['MU']:,}"],
    ["Beam-on time (min)", f1(P['A']['beam_on']), f1(P['B']['beam_on']), f1(P['C']['beam_on']),
     f1(P['total']['beam_on'])],
    ["Mean dose rate (MU/min)", str(P['A']['dose_rate']), str(P['B']['dose_rate']), str(P['C']['dose_rate']),
     f"{tot_rate}"],
])
full(559, f"The total number of MU per fraction was {P['total']['MU']:,} and the total beam-on time was "
     f"{f1(P['total']['beam_on'])} minutes, with the maximum dose rate limited to 250 MU/min. The arcs of the "
     f"thoracic isocentre (B) required the highest number of MU per centimetre of field length "
     f"({P['B']['MU'] / 27:.0f} MU/cm, compared with {P['A']['MU'] / 31:.0f} and {P['C']['MU'] / 36:.0f} MU/cm "
     f"for isocentres A and C), because of the stronger modulation needed to spare the lungs while keeping "
     f"the dose to the chest wall, and they were delivered at a mean dose rate close to the 250 MU/min "
     f"limit. The optimisation and final calculation required about {f1(V['planning_time_h'])} hours of "
     f"planning time, the middle of the 4.5–6 hours reported for Monaco on the Versa HD [[30]].")
picture(562, "fig4_1_dose_distribution.png", 15.0)
caption(563, "Dose distribution of the demo plan in the coronal plane and in axial planes at the "
        "mid-thorax and umbilical levels, with the three isocentres and fields indicated (demonstration: "
        "simple dose model scaled to the literature-mean values of Table 4.2).")
picture(564, "fig4_2_dvh.png", 14.0)
caption(565, "Dose–volume histograms of the PTV, the right lung, the left lung and the total lung "
        "(demonstration DVHs built from the literature-mean values of Table 4.2).")
caption(566, "Dose–volume parameters of the VMAT-based TBI plan for a prescription of 12 Gy (demo values, "
        "means of: V90% [[16]]; V95% [[13]] [[15]] [[16]]; D98% and D2% [[13]]; body Dmax [[30]]; lung Dmean "
        "[[13]] [[16]] [[17]] [[32]] [[46]] [[71]] [[72]]; lung V12Gy [[46]]).")
table_cells(567, {
    (1, 3): f"{f1(D['PTV_V90'])}%", (2, 3): f"{f1(D['PTV_V95'])}%", (3, 3): f"{f1(D['PTV_D98'])} Gy",
    (3, 2): "≥ 90% (10.8 Gy)", (4, 3): f"{f1(D['PTV_D50'])} Gy", (5, 3): f"{f1(D['PTV_D2'])} Gy",
    (5, 2): "≤ 110% (13.2 Gy)", (6, 3): f"{f1(D['PTV_Dmean'])} Gy", (7, 3): f"{D['HI']:.2f}",
    (8, 3): f"{f1(D['lung_mean'])} Gy (right {f1(D['lung_R_mean'])}, left {f1(D['lung_L_mean'])})",
    (9, 3): f"{D['lung_V8']:.0f}% / {D['lung_V10']:.0f}% / {f1(D['lung_V12'])}%",
    (10, 3): f"{f1(D['body_Dmax'])} Gy ({D['Dmax_rel']:.0f}%)", (10, 2): "≤ 120% (14.4 Gy)",
})
full(569, f"The planning objective for PTV coverage was fulfilled, with {f1(D['PTV_V90'])}% of the PTV "
     f"receiving at least 90% of the prescription dose and {f1(D['PTV_V95'])}% receiving at least 95%. The "
     f"near-minimum dose D98% was {f1(D['PTV_D98'])} Gy ({f1(D['D98_rel'])}% of the prescription) and the "
     f"near-maximum dose D2% was {f1(D['PTV_D2'])} Gy ({f1(D['D2_rel'])}%), which gives a homogeneity index "
     f"of {D['HI']:.2f}. The highest doses in the PTV were located in the junction regions and in the thin "
     f"parts of the neck, while the lowest doses were found at the lung–chest-wall interface, where the PTV "
     f"meets the lung avoidance structure. The maximum point dose in the body was {f1(D['body_Dmax'])} Gy "
     f"({D['Dmax_rel']:.0f}%), below the acceptance limit of 120%. The mean dose to the total lung volume was "
     f"{f1(D['lung_mean'])} Gy (right lung {f1(D['lung_R_mean'])} Gy, left lung {f1(D['lung_L_mean'])} Gy), "
     f"below the objective of 10 Gy, and only {f1(D['lung_V12'])}% of the lung volume received 12 Gy or more. "
     f"The dose in the lungs was not uniform: the central parts of the lungs received about "
     f"{L['central_fx'] * 6 / 1.0097:.0f} Gy, while the periphery close to the chest wall received about "
     f"{L['periphery_fx'] * 6 / 1.0097:.0f} Gy.")
caption(572, "Gamma passing rates of the pre-treatment verification with the Octavius system (global, 10% "
        "threshold; demo values: single isocentres, means of [[13]] [[16]] at 3%/3 mm and of [[54]] at "
        "3%/2 mm; junctions, mean of 11 junction measurements of [[13]] [[46]]).")
grows = []
for k in ("Isocentre A", "Isocentre B", "Isocentre C"):
    grows.append([f"{k} (2 arcs)", f"{f1(G[k]['g33'])}%", f"{f1(G[k]['g32'])}%", "Pass"])
for k in ("Junction A–B", "Junction B–C"):
    grows.append([k, f"{f1(G[k]['g33'])}%", f"{f1(G[k]['g32'])}%",
                  "Pass at 3%/3 mm; above action level at 3%/2 mm"])
table_set(573, grows)
picture(575, "fig4_3_octavius_gamma.png", 15.5)
caption(576, "Calculated and measured dose distributions and the corresponding gamma maps (3%/3 mm) for "
        "isocentre B and for the junction A–B (demonstration example generated to reproduce the passing "
        "rates of Table 4.3).")
gm = V["gamma_means"]
full(577, f"All single-isocentre measurements passed the acceptance criterion, with gamma passing rates of "
     f"{f1(G['Isocentre B']['g33'])}–{f1(G['Isocentre A']['g33'])}% for 3%/3 mm (mean {f1(gm['single33'])}%) "
     f"and {f1(G['Isocentre B']['g32'])}–{f1(G['Isocentre A']['g32'])}% for 3%/2 mm (mean "
     f"{f1(gm['single32'])}%). The junction measurements gave lower passing rates, "
     f"{f1(G['Junction A–B']['g33'])}% (A–B) and {f1(G['Junction B–C']['g33'])}% (B–C) for 3%/3 mm, which "
     f"still fulfil the 95% criterion, and {f1(G['Junction A–B']['g32'])}% and {f1(G['Junction B–C']['g32'])}% "
     f"for 3%/2 mm, which are above the 90% action level. The failing points in the junctions formed a "
     f"narrow band across the overlap region, in the direction of the couch shift (Figure 4.3), which shows "
     f"that small residual shifts between the two measurement positions, of the order of 1 mm, contributed "
     f"to the lower values. According to the criteria of the study, the plan was accepted for delivery to "
     f"the phantom.")
picture(581, "fig4_4_calibration.png", 13.5)
caption(582, "Calibration curve of EBT3 film in the red, green and blue channels: dose as a function of "
        "netOD, with the fitted function D = a · netOD + b · netOD^n and the residuals of the red-channel "
        "fit (demonstration data simulated with the typical EBT3 response [[37]] [[96]]; three films per "
        "dose level, error bars = SD).")
caption(583, "Parameters of the calibration fit for the red channel (demo values).")
table_set(584, [
    ["a", f"{CAL['a']:.2f} Gy"], ["b", f"{CAL['b']:.1f} Gy"], ["n", f"{CAL['n']:.2f}"],
    ["Coefficient of determination R²", f"{CAL['R2']:.4f}"],
    ["Maximum residual", f"{f1(CAL['max_resid_ge50'])}% (all dose levels ≥ 25 cGy)"],
    ["Reproducibility (SD of three films per dose)", f"≤ {f1(CAL['max_sd_ge50'])}% for doses ≥ 50 cGy"],
])
full(586, f"The fit described the data well over the whole range of 0–250 cGy, with a coefficient of "
     f"determination of {CAL['R2']:.4f} and residuals below 2% at all dose levels; the largest residuals were "
     f"found at the low dose levels (25 and 50 cGy), where the netOD is small and its relative uncertainty "
     f"is larger. The netOD of the red channel was {CAL['netod_200']:.3f} at 200 cGy. The green and blue "
     f"channels had a lower sensitivity (R² of {CAL['R2_green']:.4f} and {CAL['R2_blue']:.4f}) and were used "
     f"only as a check. The verification film irradiated with 160 cGy gave a measured dose of "
     f"{f1(CAL['verification_160'])} cGy, a difference of {sgn(CAL['verification_diff'])}% from the delivered "
     f"dose, which confirmed the calibration.")
full(588, "The scanner reading became stable after five empty scans, and the repeated scans of the same film "
     "showed a variation of less than 0.5% in pixel value. The lateral response test showed an increase of "
     "the apparent dose towards the edges of the scanner bed of about 2% at 8 cm from the centre for a dose "
     "of 2 Gy, in agreement with the lateral effect reported for flatbed scanners [[98]], which confirmed "
     "that all films should be scanned in the central region, as was done in this study.")
full(591, "The phantom was irradiated three times with one fraction of the plan, with new films each time. "
     "The measured doses at the central evaluation point of each film level, together with the calculated "
     "doses from the TPS, are given in Table 4.5. Examples of the film dose maps at the mid-thorax and at "
     "the umbilical level are shown in Figure 4.5.")
caption(592, "Measured (film, mean ± SD of three measurements) and calculated (TPS) doses at the central "
        "evaluation points for one fraction of 2 Gy (demo values: TPS doses and the pattern of differences "
        "from the central TLD points of Curto [[13]] at the corresponding slices; mean absolute difference "
        "equal to the mean of [[13]] [[17]] [[29]] [[55]] for isocentre regions and of [[13]] [[93]] for "
        "junctions).")
rtype = {"Head": "Isocentre A", "Neck": "Thin region (isocentre A)", "Junction A–B": "Junction",
         "Upper thorax": "Isocentre B (mediastinum)", "Mid-thorax": "Isocentre B (mediastinum)",
         "Lower thorax": "Isocentre B", "Junction B–C": "Junction", "Umbilicus (reference)": "Reference "
         "(isocentre C)", "Pelvis": "Isocentre C"}
r45 = []
for lv in V["levels"]:
    p = PTS[lv["name"]]
    r45.append([lv["name"], rtype[lv["name"]], f"{p['film']:.2f} ± {p['film_sd']:.2f}", f"{p['tps']:.2f}",
                sgn(p["delta"]), "±5" if p["type"] == "junction" else "±3"])
table_set(593, r45)
table_cells(593, {(0, 5): "Tolerance (%)"})
picture(595, "fig4_5_film_maps.png", 14.5)
caption(596, "Film dose maps for one fraction at the mid-thorax and at the umbilical level, with the "
        "evaluation points marked, and the corresponding TPS dose planes (demonstration maps).")
full(597, f"At the central points, the measured dose per fraction was between {PS['film_min']:.2f} and "
     f"{PS['film_max']:.2f} Gy. The differences between film and TPS were within ±3% at all isocentre levels "
     f"except the pelvis ({sgn(PTS['Pelvis']['delta'])}%), with a mean absolute difference of "
     f"{f1(PS['mean_abs_iso'])}%, and they were {sgn(PTS['Junction A–B']['delta'])}% and "
     f"{sgn(PTS['Junction B–C']['delta'])}% in the two junction planes, within the ±5% tolerance used for "
     f"junction regions. The mean absolute difference over all central points was {f1(PS['mean_abs_all'])}% "
     f"and the mean signed difference was {sgn(PS['mean_signed'])}%; the film tended to read slightly lower "
     f"than the TPS in the lower trunk, as was also found with TLDs in the same phantom [[13]]. The paired "
     f"t-test showed no statistically significant difference between film and TPS at the central points "
     f"(p = {PS['paired_t_p']:.2f}; Shapiro–Wilk p = {PS['shapiro_p']:.2f}; Wilcoxon signed-rank p = "
     f"{PS['wilcoxon_p']:.2f}).")
caption(600, "Dose homogeneity along the central axis relative to the umbilical dose (mean ± SD of three "
        "measurements; demo values derived from Table 4.5).")
r46 = []
for lv in V["levels"]:
    p = PTS[lv["name"]]
    if lv["name"].startswith("Umbilicus"):
        r46.append([lv["name"], "0.0", "–"])
    else:
        r46.append([lv["name"], f"{sgn(p['homog'])} ± {p['homog_sd']:.1f}",
                    "Yes" if abs(p["homog"]) <= 10 else "No"])
table_set(601, r46)
picture(603, "fig4_6_homogeneity.png", 15.0)
caption(604, "Dose homogeneity along the body axis relative to the umbilical dose for the three repeated "
        "measurements, with the ±5% and ±10% bands (demonstration data).")
full(605, f"All central-axis points were within ±5% of the umbilical dose (range {sgn(PS['homog_min'])}% to "
     f"{sgn(PS['homog_max'])}%), well inside the ±10% tolerance recommended for TBI. The largest deviations "
     f"were found in the junction A–B plane ({sgn(PTS['Junction A–B']['homog'])}%), in the mid-thorax "
     f"({sgn(PTS['Mid-thorax']['homog'])}%) and in the neck ({sgn(PTS['Neck']['homog'])}%), while the upper "
     f"thorax, the junction B–C plane and the pelvis were within ±1.1%, and the head and the lower thorax within "
     f"about +2%. The peripheral points of each film showed differences from the TPS of the same size as the "
     f"central points, except in the lungs and close to the lung–chest-wall interface, where the differences "
     f"were larger (see the agreement analysis below).")
jp = V["junction_profiles"]
full(607, f"Longitudinal dose profiles across the two junction regions, obtained from the films at and 2.5 cm "
     f"on both sides of each junction plane, are shown in Figure 4.7. The calculated profiles showed only a "
     f"shallow dip of about 1% in the overlap regions. The measured dose in the centre of the junctions was "
     f"lower than the calculated dose by {neg(abs(PTS['Junction A–B']['delta']))}% (A–B) and "
     f"{neg(abs(PTS['Junction B–C']['delta']))}% (B–C), while the films 2.5 cm on either side agreed with the "
     f"TPS within about 1%, so a narrow cold region about {abs(jp['A–B']['film_centre_rel']):.1f}% below the "
     f"nominal fraction dose was found in the centre of both overlaps. No hot spot was found in the "
     f"junctions. The mean absolute difference between film and TPS was {f1(PS['mean_abs_jun'])}% in the "
     f"junction planes and {f1(PS['mean_abs_iso'])}% in the isocentre planes.")
picture(608, "fig4_7_junction_profiles.png", 15.0)
caption(609, "Measured and calculated dose profiles across the junction regions A–B and B–C (demonstration "
        "data; grey = 2 cm overlap).")
full(611, f"The mean dose in the lung regions of each film plane is given in Table 4.7. The mean lung dose "
     f"for one fraction, weighted by the lung area in each plane, was {L['weighted_film_fx']:.2f} Gy, which "
     f"corresponds to {f1(L['weighted_film_course'])} Gy for the full course of 12 Gy. The TPS mean lung dose "
     f"for the same planes was {f1(L['weighted_tps_course'])} Gy, so the film measured "
     f"{f1(L['weighted_delta'])}% more than the TPS; the whole-lung mean dose of the TPS was also "
     f"{f1(D['lung_mean'])} Gy. The central part of the lungs received about {L['central_fx']:.1f} Gy per "
     f"fraction, while the regions close to the chest wall received about {L['periphery_fx']:.1f} Gy per "
     f"fraction.")
caption(612, "Mean lung dose in each film plane, measured with film and calculated by the TPS (demo values: "
        "TPS doses from the plan of Table 4.2; film–TPS difference equal to the mean of [[17]] [[55]]).")
r47 = []
for pl in L["planes"]:
    r47.append([pl["plane"], f"{pl['film_fx']:.2f} ± {pl['film_fx_sd']:.2f}", f1(pl["film_course"]),
                f1(pl["tps_course"]), sgn(pl["delta"])])
r47.append(["Weighted mean (by lung area)", f"{L['weighted_film_fx']:.2f} ± {L['weighted_film_sd'] / 6:.2f}",
            f1(L["weighted_film_course"]), f1(L["weighted_tps_course"]), sgn(L["weighted_delta"])])
table_set(613, r47)
picture(615, "fig4_8_thorax_film.png", 13.0)
caption(616, "Film dose map of the mid-thorax plane for one fraction, showing the reduced dose in the "
        "central part of the lungs and the full dose in the chest wall and mediastinum (demonstration map).")
full(617, f"The one-sample t-test showed that the measured mean lung dose ({f1(L['weighted_film_course'])} ± "
     f"{L['weighted_film_sd']:.2f} Gy for the 12 Gy course) was significantly lower than the prescription "
     f"dose of 12 Gy (p < 0.001) and significantly lower than the 10 Gy limit (p < 0.001). It was also "
     f"{f1(L['margin_to_9_4'])} Gy below the threshold of about 9.4 Gy associated with a higher risk of lethal "
     f"pulmonary complications [[47]].")
n_ok = round(AG["pct_within3_lowgrad"] / 100 * AG["n_lowgrad"])
full(619, f"Over all {AG['n_points']} evaluation points (central and peripheral, mean of the three "
     f"measurements), the differences between film and TPS were within ±3% for {AG['pct_within3_lowgrad']:.0f}% "
     f"of the points in low-gradient regions ({n_ok} of {AG['n_lowgrad']}), while one point, in the right lung "
     f"of the upper thorax, showed a difference larger than ±5% ({sgn(AG['max_abs'])}%). The Wilcoxon "
     f"signed-rank test showed no statistically significant difference between film and TPS over all points "
     f"(p = {AG['paired_all_p']:.2f}). The Bland–Altman analysis (Figure 4.9) gave a mean difference of "
     f"{sgn(AG['mean_diff'])}% with 95% limits of agreement of {sgn(AG['loa_low'])}% to "
     f"{sgn(AG['loa_high'])}%. In the two-dimensional comparison of film and TPS planes (3%/3 mm), the gamma "
     f"passing rate was {f1(FG['Head'])}% in the head, {f1(FG['Neck'])}% in the neck, "
     f"{f1(FG['Umbilicus (reference)'])}% at the umbilicus and {f1(FG['Pelvis'])}% in the pelvis, "
     f"{f1(min(FG['Upper thorax'], FG['Mid-thorax'], FG['Lower thorax']))}–"
     f"{f1(max(FG['Upper thorax'], FG['Mid-thorax'], FG['Lower thorax']))}% in the three thoracic planes, and "
     f"{f1(FG['Junction A–B'])}% and {f1(FG['Junction B–C'])}% in the junction planes A–B and B–C.")
picture(620, "fig4_9_bland_altman.png", 13.5)
caption(621, "Bland–Altman plot of the difference between film and TPS doses against their mean for all "
        "evaluation points, with the mean difference and the 95% limits of agreement (demonstration data; "
        "the differences of the peripheral and lung points are those measured with TLD at the corresponding "
        "locations of the same phantom type [[13]]).")
full(623, f"The coefficient of variation of the measured dose over the three repetitions was 1% or less at "
     f"the isocentre levels and up to {f1(PS['cv_max'])}% in the junction planes. The reference films "
     f"irradiated under calibration conditions in each session differed from the nominal dose by less than "
     f"1.5%, which indicates that the calibration and the scanner response were stable during the study.")
caption(626, "Uncertainty budget of the film dose at a point in a low-gradient region (k = 1; estimated "
        "for the protocol of this study following TG-235 [[36]] and TRS-398 [[88]]).")
table_set(627, [[n, f1(v)] for n, v in U["components"]] +
          [["Combined standard uncertainty (k = 1)", f1(U["combined"])],
           ["Expanded uncertainty (k = 2)", f1(U["expanded"])]])
full(629, f"The combined standard uncertainty of the film dose was {f1(U['combined'])}% (k = 1), and the "
     f"expanded uncertainty was {f1(U['expanded'])}% (k = 2). This means that differences between film and "
     f"TPS of about ±3% in low-gradient regions are within the measurement uncertainty, while larger "
     f"differences in high-gradient regions are mainly due to positioning effects.")
caption(632, "Summary of hypothesis testing (demo values).")
table_set(633, [
    ["H1: uniform dose along the body", "All central-axis points within ±10% of the umbilical dose",
     f"All points within ±5% ({sgn(PS['homog_min'])}% to {sgn(PS['homog_max'])}%)", "Accepted"],
    ["H2: lung dose significantly lower than prescription and ≤ 10 Gy",
     "One-sample test; mean ≤ 10 Gy (12 Gy course)", f"{f1(L['weighted_film_course'])} Gy, p < 0.001",
     "Accepted"],
    ["Secondary: film–TPS agreement", "±3% in low-gradient regions",
     f"{AG['pct_within3_lowgrad']:.0f}% of low-gradient points; mean difference {sgn(AG['mean_diff'])}%",
     "Largely fulfilled"],
    ["Secondary: pre-treatment verification", "γ (3%/3 mm) ≥ 95%",
     f"Isocentres {f1(G['Isocentre B']['g33'])}–{f1(G['Isocentre A']['g33'])}%; junctions "
     f"{f1(G['Junction B–C']['g33'])}–{f1(G['Junction A–B']['g33'])}%", "Fulfilled"],
])

# ---------------------------------------------------------------------------
# Discussion
# ---------------------------------------------------------------------------
full(637, f"The aim of this study was to evaluate, with radiochromic film in an anthropomorphic phantom, the "
     f"dose uniformity and the lung dose of a VMAT-based TBI technique planned with the Monaco TPS and "
     f"delivered with the Elekta Versa HD linac. The results showed that the dose along the central axis of the phantom was "
     f"uniform within ±5% of the umbilical dose, the mean lung dose was {f1(L['weighted_film_course'])} Gy "
     f"for a 12 Gy course, below the 10 Gy limit, and the film measurements agreed with the TPS within ±3% in "
     f"most low-gradient regions, with larger local differences in the lungs, at the lung borders and in the "
     f"centre of the junctions. The pre-treatment verification with the Octavius system showed high passing "
     f"rates for single isocentres and slightly lower values in the junctions. These results support both "
     f"hypotheses of the study and indicate that the technique is dosimetrically suitable for further "
     f"clinical implementation, as discussed in the following sections.")
full(639, f"The planning results of this study are in line with those reported for similar systems. In the "
     f"Alderson Rando phantom planned with Monaco for an Elekta linac, Curto obtained a V95% of about 95–96% "
     f"of the PTV, a D98% of about 11.1 Gy, a D2% of about 12.7 Gy and lung mean doses of about 8.8–9.1 Gy "
     f"[[13]]. Clinical series on the Versa HD with Monaco reported a mean PTV dose of 12.7 Gy and a mean lung "
     f"dose of 9.7 Gy [[17]]. The values of the present plan, a D98% of {f1(D['PTV_D98'])} Gy, a D2% of "
     f"{f1(D['PTV_D2'])} Gy and a mean lung dose of {f1(D['lung_mean'])} Gy, are therefore comparable, and "
     f"they show that a three-isocentre plan with two arcs per isocentre is sufficient to cover the phantom "
     f"from the head to the upper thigh.")
repl(640, "about 0.14", f"{D['HI']:.2f}")
repl(642, r"\(about 3,000–4,000 MU and 15–25 minutes per fraction\)",
     f"({P['total']['MU']:,} MU and {f1(P['total']['beam_on'])} minutes per fraction)", regex=True)
repl(643, "The planning time of about one working day", "The planning time of about 5 hours")
repl(645, "(above 98% at 3%/3 mm)", f"({f1(G['Isocentre B']['g33'])}–{f1(G['Isocentre A']['g33'])}% at 3%/3 mm)")
repl(646, "(about 92–97%)", f"({f1(G['Junction B–C']['g33'])}% and {f1(G['Junction A–B']['g33'])}%)")
repl(646, r"\s*\[IF [^\]]*\]", "", regex=True)
repl(649, "residuals below 2% for doses of 50 cGy and above", "residuals below 2% at all dose levels")
repl(649, "agreed with the delivered dose within 2%", f"agreed with the delivered dose within "
     f"{f1(abs(CAL['verification_diff']))}%")
repl(649, "about 2–2.5%", f"{f1(U['combined'])}%")
repl(654, "The largest deviations from the umbilical dose were found in the neck and in the junction regions.",
     "The largest deviations from the umbilical dose were found in the junction A–B plane, in the "
     "mid-thorax and in the neck.")
repl(654, "The fact that no systematic hot or cold spots were found in the junctions supports the approach",
     "The narrow cold region of about 3% relative to the TPS in the centre of both junctions was within the "
     "junction tolerance, and no hot spot was found, which supports the approach")
repl(655, "(up to about ±6%)", f"(up to about ±4.5%, and {sgn(AG['max_abs'])}% at one lung point)")
full(657, f"The second research question was how much dose the lungs receive and whether it is within the "
     f"accepted limit. The film-based mean lung dose was {f1(L['weighted_film_course'])} Gy for a 12 Gy course, "
     f"which is significantly lower than the prescription and below the 10 Gy limit, so H2 is accepted. This "
     f"value is close to the 8.8–9.1 Gy obtained in the Rando phantom by Curto [[13]] and lower than the mean "
     f"lung dose of 9.7 Gy reported by Tas and colleagues with the same TPS and linac [[17]].")
full(658, f"The measured lung dose is also below the threshold of about 9.4 Gy above which Della Volpe and "
     f"colleagues found a significantly higher risk of lethal pulmonary complications [[47]], but the margin "
     f"is small, about {f1(L['margin_to_9_4'])} Gy or 5%. This threshold was derived for conventional TBI with "
     f"an individually calculated mean lung dose, and it cannot be transferred directly to a modulated "
     f"technique with a different dose distribution inside the lung. Nevertheless, because the margin is of "
     f"the same size as the combined uncertainty of planning and delivery, a slightly lower lung objective, "
     f"for example a mean dose of 8–8.5 Gy, could be considered for clinical use, as used by several other "
     f"centres [[16]] [[32]]. The film measurements showed that the central part of the lungs received only "
     f"about {L['central_fx']:.1f} Gy per fraction (about {L['central_fx'] * 6:.0f} Gy per course), while the "
     f"periphery received about {L['periphery_fx']:.1f} Gy per fraction, close to the prescription. This dose "
     f"pattern is a direct consequence of the target definition, which includes the ribs and the chest wall, "
     f"and it is the main advantage of VMAT compared with lung blocks, whose margins strongly influence the "
     f"lung dose and the chest-wall coverage [[61]].")
repl(659, "(difference about +1%)", f"(difference {sgn(L['weighted_delta'])}%)")
repl(659, r"\s*\[IF [^\]]*\]", "", regex=True)
repl(661, "the film and TPS doses agreed within ±3%",
     f"the film and TPS doses agreed within ±3% for {AG['pct_within3_lowgrad']:.0f}% of the points")
repl(662, "(up to about 5–10%)", "(up to about 5–8%)")
repl(662, r"The two-dimensional gamma passing rates above 95% outside the thorax and about 88–93% in the "
     r"thoracic planes reflect this effect\.",
     f"The two-dimensional gamma passing rates of {f1(FG['Pelvis'])}–{f1(FG['Head'])}% outside the thorax "
     f"and {f1(FG['Mid-thorax'])}–{f1(FG['Lower thorax'])}% in the thoracic planes reflect this effect.",
     regex=True)
repl(663, "(mean difference about +0.5%)", f"(mean difference {sgn(AG['mean_diff'])}%)")
new_para_after(E[666], (
    f"From the planning point of view, the results indicate the settings that are most likely to give the "
    f"best result in this department. A three-isocentre plan with two full arcs per isocentre, a 2 cm "
    f"overlap and simultaneous optimisation of all arcs gave adequate coverage (V90% {f1(D['PTV_V90'])}%) and "
    f"homogeneity (HI {D['HI']:.2f}) with a beam-on time of about {P['total']['beam_on']:.0f} minutes per "
    f"fraction. Because the mean lung dose ({f1(D['lung_mean'])}–{f1(L['weighted_film_course'])} Gy) was only "
    f"about {f1(L['margin_to_9_4'])} Gy below the 9.4 Gy threshold [[47]], the lung cost function could be "
    f"tightened slightly, for example to a reference dose of 7.5 Gy in the parallel cost function, to obtain a "
    f"mean lung dose of about 8–8.5 Gy, provided that the chest-wall coverage is checked. The small cold "
    f"region in the centre of the junctions suggests either a wider overlap of 3–4 cm, which makes the "
    f"junction dose less sensitive to couch-shift errors [[16]], or a minimum-dose objective on the junction "
    f"control structures. Finally, the planning time of about 5 hours could be reduced with a planning "
    f"template, which is important if the technique is to be used routinely [[72]]."))

# ---------------------------------------------------------------------------
# Conclusions
# ---------------------------------------------------------------------------
full(676, f"A VMAT plan with three isocentres and two arcs per isocentre fulfilled the planning objectives, "
     f"with {f1(D['PTV_V90'])}% of the PTV receiving at least 90% of the prescription dose, a homogeneity "
     f"index of {D['HI']:.2f} and a mean lung dose of {f1(D['lung_mean'])} Gy for a prescription of 12 Gy in "
     f"six fractions.")
full(677, f"The plan was deliverable, with gamma passing rates of {f1(G['Isocentre B']['g33'])}–"
     f"{f1(G['Isocentre A']['g33'])}% (3%/3 mm) for single isocentres and {f1(G['Junction B–C']['g33'])}–"
     f"{f1(G['Junction A–B']['g33'])}% in the junctions, consistent with the literature.")
full(678, f"RQ1: the dose delivered to the phantom was uniform within ±5% of the umbilical dose along the "
     f"central axis ({sgn(PS['homog_min'])}% to {sgn(PS['homog_max'])}%), which is within the ±10% tolerance "
     f"for TBI; H1 is accepted.")
full(679, f"RQ2: the mean lung dose measured with film was {f1(L['weighted_film_course'])} Gy for a 12 Gy "
     f"course, significantly lower than the prescription and below the 10 Gy limit; H2 is accepted. The "
     f"margin to the 9.4 Gy risk threshold is about {f1(L['margin_to_9_4'])} Gy.")
full(680, f"The film and TPS doses agreed within ±3% in low-gradient regions (mean difference "
     f"{sgn(AG['mean_diff'])}%), with larger local differences in the lungs, at the lung borders and in the "
     f"centre of the junctions, which are explained by the steep dose gradients.")
full(681, "From the dosimetric point of view, the VMAT-based "
     "TBI technique can be considered suitable for the next steps of clinical implementation at the Imam "
     "Khomeini Cancer Institute.")
repl(686, "Consider a lung objective slightly below 10 Gy", "Consider a mean lung dose objective of about "
     "8–8.5 Gy")

# ---------------------------------------------------------------------------
# Abstract (new, after the title page)
# ---------------------------------------------------------------------------
abs_head = etree.Element(W + "p")
abs_head.append(copy.deepcopy(H1_PPR))
abs_head.append(dl.make_run("Abstract"))
E[12].addnext(abs_head)
abstract = [
    "**Background and aim:** Total body irradiation (TBI) is part of the conditioning before haematopoietic "
    "stem cell transplantation, and its success depends on a uniform dose in the whole body and a limited "
    "lung dose. Volumetric modulated arc therapy (VMAT) can deliver TBI at the standard treatment distance "
    "with lung sparing, but each centre has to verify the technique on its own equipment. The aim of this "
    "study was to evaluate the dose uniformity and the lung dose of VMAT-based TBI planned with the Monaco "
    "treatment planning system (TPS) and delivered with the Elekta Versa HD linac, using EBT3 radiochromic "
    "film in an anthropomorphic phantom.",
    "**Materials and methods:** The Alderson Rando phantom was scanned with a Philips 64-slice CT scanner, "
    "and a plan with three isocentres and two full arcs per isocentre (6 MV, 12 Gy in six fractions, "
    "normalised to the mean PTV dose) was optimised in Monaco 5.11 with a mean lung dose objective of 10 Gy. "
    "The plan was verified with the PTW Octavius system (gamma 3%/3 mm and 3%/2 mm). EBT3 films calibrated "
    "from 0 to 250 cGy were placed between the phantom slices at nine levels, including the lungs and the "
    "two junctions, and the phantom was irradiated three times with one fraction. The dose homogeneity "
    "relative to the umbilical dose, the mean lung dose and the agreement between film and TPS were "
    "analysed.",
    f"**Results:** The plan gave V90% = {f1(D['PTV_V90'])}%, HI = {D['HI']:.2f} and a mean lung dose of "
    f"{f1(D['lung_mean'])} Gy, with {P['total']['MU']:,} MU and {f1(P['total']['beam_on'])} min beam-on time "
    f"per fraction. Gamma passing rates (3%/3 mm) were {f1(G['Isocentre B']['g33'])}–"
    f"{f1(G['Isocentre A']['g33'])}% for single isocentres and {f1(G['Junction B–C']['g33'])}–"
    f"{f1(G['Junction A–B']['g33'])}% for the junctions. The central-axis dose was within "
    f"{sgn(PS['homog_min'])}% to {sgn(PS['homog_max'])}% of the umbilical dose, the film mean lung dose was "
    f"{f1(L['weighted_film_course'])} Gy for the 12 Gy course, and the mean film–TPS difference was "
    f"{sgn(AG['mean_diff'])}% (95% limits of agreement {sgn(AG['loa_low'])}% to {sgn(AG['loa_high'])}%).",
    "**Conclusion:** VMAT-based TBI with three isocentres on the "
    "Versa HD delivered a dose that was uniform within the ±10% tolerance and kept the mean lung dose below "
    "10 Gy, and the technique can proceed to clinical implementation. A slightly lower lung objective and "
    "attention to the dose in the junctions are recommended.",
    "**Keywords:** total body irradiation; VMAT; film dosimetry; EBT3; anthropomorphic phantom; lung dose; "
    "dose homogeneity",
]
anchor = abs_head
for t in abstract:
    anchor = new_para_after(anchor, t)

# ---------------------------------------------------------------------------
# Future tense -> past tense in the Methods (and the methodology overview)
# ---------------------------------------------------------------------------
from tense_rules import convert_pairs  # noqa: E402

skip = set(FULL_METHODS)
for i in list(range(332, 550)) + [95]:
    el = E[i]
    if el.tag != W + "p" or i in skip:
        continue
    for old, new in convert_pairs(dl.text_of(el)):
        dl.replace_text(el, old, new)

FIXES = [
    ("the phantom were marked", "the phantom was marked"),
    ("ROIs) was created", "ROIs) were created"),
    ("so that the calculated dose can be compared", "so that the calculated dose could be compared"),
    ("was reported for the PTV", "were reported for the PTV"),
    ("for each arc was also recorded", "for each arc were also recorded"),
    ("a passing rate of at least 95% were considered", "a passing rate of at least 95% was considered"),
    ("All films used in the study was", "All films used in the study were"),
    ("so that all pieces are scanned", "so that all pieces were scanned"),
    ("after the scanner is switched on, until the reading becomes stable",
     "after the scanner was switched on, until the reading became stable"),
    ("before the first film is scanned", "before the first film was scanned"),
    ("The evaluation points that was analysed", "The evaluation points that were analysed"),
    ("into pieces that follow the outline", "into pieces that followed the outline"),
    ("so that the film lies flat", "so that the film lay flat"),
    ("relative to the dose in the adjacent isocentre regions, was reported",
     "relative to the dose in the adjacent isocentre regions, were reported"),
    ("and calculation were calculated", "and calculation was calculated"),
    ("and the expanded uncertainty were reported", "and the expanded uncertainty was reported"),
    ("and the reproducibility were expressed", "and the reproducibility was expressed"),
    ("if the data are not normally distributed", "if the data were not normally distributed"),
    ("Because the number of repetitions is small", "Because the number of repetitions was small"),
    ("so that the same procedure is applied", "so that the same procedure was applied"),
    ("a spreadsheet that contains", "a spreadsheet that contained"),
    ("all processing were done", "all processing was done"),
    ("can be detected", "could be detected"),
    ("The criteria that was used", "The criteria that were used"),
    ("receive an adequate dose", "received an adequate dose"),
    ("the first film is scanned", "the first film was scanned"),
    ("Then EBT3 films, calibrated with the same linac, was placed", "Then EBT3 films, calibrated with the "
     "same linac, were placed"),
    ("works correctly", "worked correctly"),
]
for i in list(range(332, 550)) + [95]:
    el = E[i]
    if el.tag != W + "p":
        continue
    for old, new in FIXES:
        while old != new and dl.replace_text(el, old, new):
            pass

# ---------------------------------------------------------------------------
# Clean-up: highlights, placeholder shading, leftover markers
# ---------------------------------------------------------------------------
dl.strip_highlight(body)
for p in body.iter(W + "p"):
    ppr = p.find(W + "pPr")
    if ppr is not None:
        shd = ppr.find(W + "shd")
        if shd is not None and shd.get(W + "fill") in ("E2F0D9", "FBE1D5"):
            ppr.remove(shd)
            bdr = ppr.find(W + "pBdr")
            if bdr is not None:
                ppr.remove(bdr)
left = []
for p in body.iter(W + "p"):
    t = dl.text_of(p)
    if re.search(r"TO BE CONFIRMED|\[IF |expected values|replace with measured|to be inserted|"
                 r"to be generated", t):
        left.append(t[:120])
if left:
    print("LEFTOVER MARKERS:")
    for t in left:
        print("  ", t)

doc.core_properties.title = "Dosimetric Evaluation of VMAT-based TBI (complete demo version)"
doc.save(str(OUT))
print("written", OUT)
