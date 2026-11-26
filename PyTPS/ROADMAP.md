# PyTPS roadmap

## 0.1 (done)
Import (DICOM CT + RT Structure Set, phantoms), viewer, contouring, manual beams and arcs, MLC (open,
conformal, manual), wedges, divergent beam display, BEV with DRR, 3D model, pencil-beam dose, MU,
normalisation, isodoses, DVH, statistics.

## 0.2 (next)
1. IMRT Constraints tab: cost functions per structure (target penalty, target EUD, quadratic under/overdose,
   under/overdose DVH, maximum dose, serial, parallel, conformality), objective or constraint, weights,
   layering; achieved values shown after optimisation.
2. Optimisation tab: Stage 1 fluence optimisation (static IMRT beams and VMAT arcs) on the pencil-beam engine,
   Stage 2 MLC sequencing (step-and-shoot segments; one aperture per VMAT control point with leaf-speed and
   dose-rate limits), segment weight optimisation, MU and delivery time; cost history plot.
3. Plans: several plans per patient, plan comparison (DVH overlay, statistics side by side), plan sum,
   dose difference display.
4. DICOM: RT Plan export/import (beam geometry, control points, MU) and RT Dose export/import; compare an
   imported clinical dose with the PyTPS dose.
5. Beam data editor (Tools menu): PDD, output factors, wedge factors, refit and show the fit quality.
6. Point doses, clinical goals with pass/fail, PDF plan report.
7. Tests for each item; screenshots in CI; Windows build.
