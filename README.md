# PyTPS — educational radiotherapy treatment planning system

PyTPS is a desktop program for **teaching treatment planning** to medical physics students (MSc level).
It follows the workflow of a modern planning system: patient import, contouring, beams, prescription,
dose calculation and plan evaluation. It has its own design and is not affiliated with any vendor.

> **Not for clinical use.** PyTPS is not a medical device, is not commissioned for any treatment machine
> and must not be used to plan, check or deliver patient treatments. The beam data are generic teaching values.

## Features (version 0.1)

- **Patient**: import DICOM CT, RT Structure Set (read locally; names and IDs are replaced by an anonymous
  code), practice phantoms (water, thorax, pelvis, head and neck, breast, whole body for TBI),
  editable CT-to-electron-density table.
- **Viewer**: linked transverse, coronal and sagittal views, 2 × 2 / one large + three / single layouts,
  window/level presets and mouse window/level, zoom, pan, measuring.
- **Contouring**: brush, eraser, polygon (add or subtract), 3D margins (different head-foot margin),
  Boolean operations, threshold, interpolation between slices, fill holes, keep largest part,
  body outline from CT, structure types, colours and density overrides, undo / redo,
  export as RT Structure Set.
- **Beams** (added and edited by hand): static fields and arcs, isocentre (typed, at the crosshair or the
  target centre), gantry, collimator, couch, jaws, energy (6 and 10 MV), MLC (open, conformal to a structure
  with margin, manual leaf editing in the beam's eye view), wedges, opposed beams, copy, weights,
  patient position (HFS, FFS, HFP, FFP), source–skin distance.
- **Beam display**: divergent field outlines in all slices, central axis, arc control points,
  beam's eye view with digitally reconstructed radiograph (DRR), projected structures, jaws and MLC
  (drag the jaws and leaves), and a 3D model of patient and beams.
- **Dose**: pencil-beam calculation (fluence convolution with penumbra and scatter kernels, radiological
  depth through the density volume), MU calculation and normalisation (isocentre, mean, D95, D50,
  prescription isodose), isodose lines or colour wash.
- **Evaluation**: DVH, dose statistics per structure (min, mean, max, D98, D95, D50, D2, V95%), beam MU and
  SSD table, CSV export.
- **Beam data**: generic 6 MV and 10 MV data (PDD for several field sizes, output factors, head scatter,
  wedge factors); the model parameters are fitted to the data, as in commissioning.

Planned next: IMRT constraints and inverse optimisation (IMRT, VMAT), plan comparison and plan sum,
RT Plan / RT Dose import and export, beam data editor, DICOM export of the plan.

## Run from source

```
python -m pip install -r requirements.txt
python run_pytps.py                       # or: python -m pytps
python run_pytps.py --phantom "Thorax (lung tumour)" --demo-plan 0,90,180,270
```

Python 3.10 or newer. Tested on Windows and Linux. A 4 mm dose grid needs about 1–2 GB of memory for a pelvis or thorax CT.

## Windows program

The GitHub Actions workflow *PyTPS* builds a Windows folder program with PyInstaller
(Actions ▸ PyTPS ▸ Run workflow ▸ "Build the Windows program"). Download the `PyTPS-windows` artifact
and start `PyTPS.exe`.

## Mouse and keys

| Action | How |
|---|---|
| Move the crosshair | left click (crosshair tool) |
| Change slice | mouse wheel, ↑ / ↓, Page Up / Page Down (Shift + wheel = 5 slices) |
| Zoom / pan | Ctrl + wheel / middle button drag |
| Window / level | right button drag, or the presets |
| Brush size | spin box in the toolbar |
| Polygon | click points, double-click or right-click to close; Shift = subtract |
| Undo / redo | Ctrl + Z / Ctrl + Y |
| Calculate dose | F5 |

## Coordinate conventions

Patient coordinates are DICOM (LPS, mm): +x patient left, +y posterior, +z head. For a head-first
supine patient, gantry 0° is an anterior beam and gantry 90° enters from the patient's left.
Field coordinates X and Y are at the isocentre plane; MLC leaves move along X.

## Licence

MIT, see `LICENSE`. Data you import stay on your computer; please use de-identified data and follow the rules
of your institution.
