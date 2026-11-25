from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.units import mm
import math

# ── Page setup ──────────────────────────────────────────────────────────────
W, H = A4          # 595 x 842 pt
OUT  = "/home/claude/vmat_tbi_flowchart.pdf"

c = canvas.Canvas(OUT, pagesize=A4)
c.setTitle("VMAT-based TBI – Study Methodology Flowchart")
c.setAuthor("Negina Farhady · TUMS-IC")

# ── Color palette ────────────────────────────────────────────────────────────
NAVY   = HexColor("#185FA5")   # header
BLUE   = HexColor("#378ADD")   # planning steps
TEAL   = HexColor("#0F6E56")   # planning/verification
AMBER  = HexColor("#BA7517")   # calibration
CORAL  = HexColor("#993C1D")   # irradiation
GREEN  = HexColor("#3B6D11")   # analysis
PURPLE = HexColor("#534AB7")   # title band / goal band
GRAY   = HexColor("#5F5E5A")   # sub-boxes text
LGRAY  = HexColor("#F1EFE8")   # sub-box fill
DGRAY  = HexColor("#888780")   # diamond border
BG     = HexColor("#EEF4FF")   # light tinted fill for main boxes
BG_T   = HexColor("#E1F5EE")   # teal bg
BG_A   = HexColor("#FAEEDA")   # amber bg
BG_C   = HexColor("#FAECE7")   # coral bg
BG_G   = HexColor("#EAF3DE")   # green bg
BG_P   = HexColor("#EEEDFE")   # purple bg

# ── Drawing helpers ──────────────────────────────────────────────────────────
def rr(x, y, w, h, r, fill, stroke_col, lw=0.5):
    """Rounded rect. y is top-left in our coord (will be flipped)."""
    c.setFillColor(fill)
    c.setStrokeColor(stroke_col)
    c.setLineWidth(lw)
    c.roundRect(x, H - y - h, w, h, r, stroke=1, fill=1)

def txt(text, x, y, size=9, color=black, bold=False, align="center", w=0):
    """Text. y is distance from top. align: center/left/right."""
    c.setFillColor(color)
    font = "Helvetica-Bold" if bold else "Helvetica"
    c.setFont(font, size)
    yp = H - y
    if align == "center":
        c.drawCentredString(x, yp, text)
    elif align == "left":
        c.drawString(x, yp, text)
    else:
        c.drawRightString(x, yp, text)

def arrow(x1, y1, x2, y2, color=NAVY):
    """Vertical/horizontal arrow."""
    c.setStrokeColor(color)
    c.setLineWidth(0.8)
    c.line(x1, H - y1, x2, H - y2)
    # arrowhead at (x2, y2)
    dx = x2 - x1; dy = y2 - y1
    length = math.sqrt(dx*dx + dy*dy)
    if length == 0: return
    ux, uy = dx/length, dy/length
    # perpendicular
    px, py = -uy, ux
    size = 5
    ax, ay = x2 - ux*size, y2 - uy*size
    c.setFillColor(color)
    p = c.beginPath()
    p.moveTo(x2, H - y2)
    p.lineTo(ax + px*size*0.4, H - (ay + py*size*0.4))
    p.lineTo(ax - px*size*0.4, H - (ay - py*size*0.4))
    p.close()
    c.drawPath(p, fill=1, stroke=0)

def hline(x1, x2, y, color=DGRAY, lw=0.6):
    c.setStrokeColor(color); c.setLineWidth(lw)
    c.line(x1, H - y, x2, H - y)

def vline(x, y1, y2, color=DGRAY, lw=0.6):
    c.setStrokeColor(color); c.setLineWidth(lw)
    c.line(x, H - y1, x, H - y2)

# ── Layout constants ─────────────────────────────────────────────────────────
MX   = 22          # left margin
CX   = W / 2       # centre x
BW   = W - 2*MX    # box width (551 pt)
SBW  = (BW - 8) / 2  # split-box width

# row y-tops (distance from page top)
y = 14

# ╔══════════════════════════════════════════════╗
# ║  TITLE BAND                                  ║
# ╚══════════════════════════════════════════════╝
TH = 30
rr(MX, y, BW, TH, 8, BG_P, PURPLE, lw=0.8)
txt("VMAT-based TBI — Study Methodology Flowchart", CX, y+11, 11, PURPLE, bold=True)
txt("M.Sc. Thesis  ·  Tehran University of Medical Sciences  ·  Imam Khomeini Hospital", CX, y+22, 8, HexColor("#3C3489"))
y += TH + 7

# ────────────────────────────────────────────────────────────────────────────
def step_box(label, sub, bg, col, step_num):
    """Standard step box: 34 pt tall, label + subtitle."""
    global y
    SH = 34
    rr(MX, y, BW, SH, 6, bg, col, lw=0.7)
    txt(f"Step {step_num}  —  {label}", CX, y+12, 9.5, col, bold=True)
    txt(sub, CX, y+24, 8, GRAY)
    y += SH

def sub_box_full(text, text2=""):
    """Full-width subtle grey annotation box."""
    global y
    SH = 17 if not text2 else 26
    rr(MX+6, y, BW-12, SH, 4, LGRAY, HexColor("#B4B2A9"), lw=0.4)
    if text2:
        txt(text,  CX, y+9,  7.5, GRAY)
        txt(text2, CX, y+19, 7.5, GRAY)
    else:
        txt(text, CX, y+10, 7.5, GRAY)
    y += SH

def sub_row(texts, bg_col, str_col):
    """Two or three equal sub-boxes side by side."""
    global y
    n = len(texts)
    gap = 5
    w = (BW - (n-1)*gap) / n
    SH = 30
    for i, (title, body) in enumerate(texts):
        x0 = MX + i*(w+gap)
        rr(x0, y, w, SH, 4, LGRAY, HexColor("#B4B2A9"), lw=0.4)
        txt(title, x0 + w/2, y+10, 7.5, str_col, bold=True)
        txt(body,  x0 + w/2, y+21, 7,   GRAY)
    y += SH

def connector(gap=7):
    global y
    arrow(CX, y, CX, y + gap, NAVY)
    y += gap

def acceptance_box():
    global y
    SH = 24
    rr(MX, y, BW, SH, 6, LGRAY, DGRAY, lw=0.6)
    txt("Acceptance criteria", CX, y+9, 8.5, GRAY, bold=True)
    txt("Dose uniformity ±10%   ·   Prescribed dose accuracy ±3%   ·   Lung mean dose ≤ 10 Gy", CX, y+19, 7.5, GRAY)
    y += SH

# ════════════════════════════════════════════════════════════════════════════
# STEP 1
connector(5)
step_box("Phantom Setup & CT Acquisition",
         "Alderson Rando phantom  ·  Supine position  ·  Whole-body CT  ·  5 mm slice thickness",
         BG, NAVY, 1)

connector()
# STEP 2
step_box("Contouring  (DICOM transfer to Monaco TPS)",
         "Outer body contour  ·  Lungs (2 mm inner margin)  ·  PTV = whole body minus 3 mm skin",
         BG, BLUE, 2)
sub_box_full("PTV divided into 3–4 sub-PTVs based on body length for a clinically deliverable plan")

connector()
# STEP 3
step_box("Treatment Planning  (Monaco 5.11 TPS)",
         "3 isocenters  ·  2 arcs each (CW + CCW)  ·  6 MV photons  ·  12 Gy in 6 × 2 Gy fractions",
         BG_T, TEAL, 3)
sub_row([
    ("Dose prescription", "95% PTV ← 90% Rx dose"),
    ("Lung constraint",   "Mean dose ≤ 10 Gy"),
    ("Max dose rate",     "250 MU/min (50–600 range)"),
], LGRAY, TEAL)

connector()
# STEP 4
step_box("Plan Verification  (QA)",
         "PTW Octavius phantom (50 cm)  ·  Face-in & face-out positions  ·  Inclinometer synchronisation",
         BG_T, TEAL, 4)
sub_box_full("Gamma evaluation (Low's method):  dose difference 3%  ·  distance-to-agreement 3 mm")

# ── Decision diamond ─────────────────────────────────────────────────────────
connector()
DY = 28      # diamond half-height
DX = 42      # diamond half-width
dx = CX; dy_top = y
# draw diamond
c.setFillColor(LGRAY); c.setStrokeColor(DGRAY); c.setLineWidth(0.7)
p = c.beginPath()
p.moveTo(dx, H - dy_top)
p.lineTo(dx + DX, H - (dy_top + DY))
p.lineTo(dx, H - (dy_top + 2*DY))
p.lineTo(dx - DX, H - (dy_top + DY))
p.close()
c.drawPath(p, fill=1, stroke=1)
txt("QA pass?", CX, dy_top + DY - 4, 8.5, GRAY, bold=True)
txt("\u03b3 \u2265 95%", CX, dy_top + DY + 6, 8, GRAY)

# Fail branch (left loop)
fail_x = MX - 5
c.setStrokeColor(DGRAY); c.setLineWidth(0.6)
c.line(dx - DX, H - (dy_top + DY), fail_x, H - (dy_top + DY))
# go up to step 3 top
step3_top = 14 + 30 + 7 + 7 + 34 + 7 + 34 + 17 + 7 + 34 + 30 + 7  # approx - use anchor
# Just go up to roughly step 3 entry area visually
up_y = dy_top + DY
loop_top = 115  # approximate y for top of step 3

c.line(fail_x, H - up_y, fail_x, H - loop_top)
arrow(fail_x, loop_top, MX, loop_top, DGRAY)
txt("Fail", fail_x - 3, dy_top + DY - 4, 7, GRAY, align="right")
txt("Re-plan", fail_x - 3, loop_top + 14, 7, GRAY, align="right")

# Pass label + arrow
txt("Pass", CX + DX//2 + 10, dy_top + 2*DY + 3, 7.5, GRAY)
y = dy_top + 2*DY
connector()

# STEP 5
step_box("EBT3 Gafchromic Film Calibration",
         "Films cut 5×5 cm  ·  Perspex slab (10 layers)  ·  11 dose levels: 0 – 250 cGy  ·  3 repeats",
         BG_A, AMBER, 5)
sub_row([
    ("Exposure conditions", "SAD 100 cm · 200 cGy/min · 10×10 cm\xb2"),
    ("Scanning protocol",   "Microtek 9800XL · 150 dpi · RGB · TIFF"),
], LGRAY, AMBER)
sub_box_full("Net OD = log(I_unexposed / I_exposed)   \u2192   calibration curve (Optical Density vs. Dose)")

connector()
# STEP 6
step_box("Phantom Irradiation  (Versa HD\u2122 Linac)",
         "Elekta Agility MLC (160 leaves · 5 mm min · 40\xd740 cm\xb2 max field)  ·  3 repetitions",
         BG_C, CORAL, 6)
sub_box_full("EBT3 films inserted at organ positions (including lung region) throughout the phantom")

connector()
# STEP 7
step_box("Film Scanning & Image Processing  (ImageJ)",
         "Scan in TIFF  ·  Averaging filter  ·  ROI = 1\xd71 cm centre  ·  Extract R / G / B channels",
         BG_C, CORAL, 7)
sub_box_full("Pixel values in ROI \u2192 Net OD per channel \u2192 dose via calibration curve")

connector()
# STEP 8 header
SH = 22
rr(MX, y, BW, SH, 6, BG_G, GREEN, lw=0.7)
txt("Step 8  \u2014  Data Analysis", CX, y+13, 9.5, GREEN, bold=True)
y += SH

# Two branches
branch_top = y
connector(7)
split_y = y  # where lines split

# left arrow
c.setStrokeColor(GREEN); c.setLineWidth(0.7)
c.line(MX + SBW/2 + 4, H - split_y, MX + SBW/2 + 4, H - (split_y + 6))
arrow(MX + SBW/2 + 4, split_y + 6, MX + SBW/2 + 4, split_y + 9, GREEN)
# right arrow
rx = MX + SBW + 8 + SBW/2
c.line(rx, H - split_y, rx, H - (split_y + 6))
arrow(rx, split_y + 6, rx, split_y + 9, GREEN)

y = split_y + 9

# Left branch box
SH2 = 48
rr(MX, y, SBW, SH2, 6, BG_G, GREEN, lw=0.6)
txt("Dose uniformity", MX + SBW/2, y+11, 9, GREEN, bold=True)
txt("Homogeneity% =", MX + SBW/2, y+23, 8, GRAY)
txt("(D_point \u2212 D_umbilicus) / D_umbilicus \xd7 100", MX + SBW/2, y+33, 7.5, GRAY)
txt("Acceptance: \xb110% of prescribed dose", MX + SBW/2, y+44, 7, GRAY)

# Right branch box
rr(MX + SBW + 8, y, SBW, SH2, 6, BG_G, GREEN, lw=0.6)
txt("Critical organ dose", MX + SBW + 8 + SBW/2, y+11, 9, GREEN, bold=True)
txt("Films at organ positions in phantom", MX + SBW + 8 + SBW/2, y+23, 8, GRAY)
txt("Primary OAR: lungs", MX + SBW + 8 + SBW/2, y+33, 7.5, GRAY)
txt("Lung mean dose constraint \u2264 10 Gy", MX + SBW + 8 + SBW/2, y+44, 7, GRAY)

# Merge lines
merge_y = y + SH2
c.setStrokeColor(GREEN); c.setLineWidth(0.6)
c.line(MX + SBW/2 + 4, H - merge_y, MX + SBW/2 + 4, H - (merge_y + 6))
c.line(rx, H - merge_y, rx, H - (merge_y + 6))
c.line(MX + SBW/2 + 4, H - (merge_y + 6), rx, H - (merge_y + 6))
arrow(CX, merge_y + 6, CX, merge_y + 9, GREEN)
y = merge_y + 9

# Acceptance criteria
acceptance_box()
connector(6)

# Goal band
SH = 22
rr(MX, y, BW, SH, 6, BG_P, PURPLE, lw=0.7)
txt("Goal: commission VMAT-based TBI technique at Imam Khomeini Hospital Cancer Institute", CX, y+13, 8.5, PURPLE, bold=True)
y += SH

# ── Footer ──────────────────────────────────────────────────────────────────
c.setFillColor(HexColor("#B4B2A9"))
c.setFont("Helvetica", 6.5)
c.drawCentredString(CX, 10, "Negina Farhady  ·  M.Sc. Medical Physics  ·  TUMS-IC  ·  Cancer Institute, Imam Khomeini Hospital")

c.save()
print(f"PDF saved: {OUT}  (page height used: {y:.0f} pt of {H:.0f} pt)")