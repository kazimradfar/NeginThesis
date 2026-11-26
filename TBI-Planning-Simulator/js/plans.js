/* RT Planning Simulator — teaching presets (phantom + technique + beams + cost functions + clinical goals).
 * Dose levels and goals follow common textbook values; they are starting points for practice, not protocols. */
"use strict";
const PLANS = (() => {
  const P0 = { smoothing: "Medium", iters1: 200, iters2: 80, leafSpeed: 3.5, gantrySpeed: 6, maxDoseRate: 600,
    minArea: 4, minMU: 2, maxSegs: 10, levels: 7, vmatLevels: 5, vmatSegs: 6, vmatMinArea: 1, apThr: 0.3, grid: null };
  const iso = (x, y, z) => ({ x, y, z });
  function arc(name, I, dir, X1, X2, Y1, Y2, o = {}) {
    return Object.assign({ name, type: "arc", iso: { ...I }, start: dir === "CW" ? 181 : 179, stop: dir === "CW" ? 179 : 181, dir, gantry: 0,
      coll: 0, X1, X2, Y1, Y2, energy: "6 MV", orient: "HFS", mlc: "optimised", weight: 1, part: 1, sad: 100 }, o);
  }
  function fld(name, I, g, X1, X2, Y1, Y2, o = {}) {
    return Object.assign({ name, type: "static", iso: { ...I }, gantry: g, start: 181, stop: 179, dir: "CW",
      coll: 0, X1, X2, Y1, Y2, energy: "6 MV", orient: "HFS", mlc: "optimised", weight: 1, part: 1, sad: 100 }, o);
  }
  const ob = (struct, type, dose, extra, weight = 1, on = true, mode = "objective") => ({ on, struct, type, dose, extra, weight, mode });
  const goal = (struct, metric, x, op, limit, lit) => ({ struct, metric, x, op, limit, lit });
  const plan = (o) => Object.assign({ rx: 12, fx: 6, target: "PTV", norm: "mean", layering: false, cpStep: 10, technique: "VMAT",
    params: { ...P0 }, beams: [], objectives: [], goals: [] }, o, { params: { ...P0, ...(o.params || {}) } });

  // ------------------------------------------------------------------ TBI
  function tbiIsos(list) {
    const out = [];
    list.forEach(([n, z, lo, hi, arcs = 2, part = 1, orient = "HFS"], i) => {
      for (let a = 0; a < arcs; a++) out.push(arc(`${n}${a + 1}`, iso(0, 0, z), a % 2 ? "CCW" : "CW", -20, 20, lo, hi, { part, orient }));
    });
    return out;
  }
  const tbiObj = () => [
    ob("PTV", "Target Penalty", 12.0, 95), ob("PTV", "Quadratic Overdose", 13.2, 0.3),
    ob("Lungs", "Parallel", 8.0, 55), ob("Lungs", "Quadratic Overdose", 10.0, 0.5, 0.5),
    ob("Body", "Maximum Dose", 14.4, 0), ob("Kidneys", "Quadratic Overdose", 10.0, 0.5, 0.5, false),
  ];
  const tbiGoals = (lit = true) => [
    goal("PTV", "V", 10.8, ">=", 95, lit ? 98.8 : null), goal("PTV", "V", 11.4, ">=", 90, lit ? 96.5 : null),
    goal("PTV", "D", 98, ">=", 10.8, lit ? 11.0 : null), goal("PTV", "D", 50, "", null, lit ? 12.0 : null),
    goal("PTV", "D", 2, "<=", 13.2, lit ? 12.8 : null), goal("PTV", "HI", null, "<=", 0.2, lit ? 0.15 : null),
    goal("Lungs", "Dmean", null, "<=", 10, lit ? 8.8 : null), goal("Lungs", "V", 12, "<=", 10, lit ? 4.5 : null),
    goal("Kidneys", "Dmean", null, "<=", 12, null),
    goal("Body", "Dmax", null, "<=", 14.4, lit ? 14.2 : null), goal("Body", "MU", null, "", null, lit ? 3581 : null),
  ];
  const THESIS = [["A", 15.5, -15.5, 15.5], ["B", 42.5, -13.5, 13.5], ["C", 72.0, -18.0, 18.0]];

  const LIST = [
    { id: "tbi-thesis", phantom: "rando", label: "TBI · VMAT 3 isocentres (thesis plan)", make: () => plan({
      name: "VMAT-TBI, 3 isocentres", technique: "VMAT", params: { maxDoseRate: 250 }, beams: tbiIsos(THESIS), objectives: tbiObj(), goals: tbiGoals() }) },
    { id: "tbi-overlap4", phantom: "rando", label: "TBI · wider overlap (4 cm)", make: () => plan({
      name: "VMAT-TBI, 4 cm overlap", params: { maxDoseRate: 250 }, beams: tbiIsos([["A", 15.5, -15.5, 16.5], ["B", 42.5, -14.5, 14.5], ["C", 72.0, -19.0, 18.0]]), objectives: tbiObj(), goals: tbiGoals() }) },
    { id: "tbi-lung75", phantom: "rando", label: "TBI · stricter lungs (Parallel 7.5 Gy)", make: () => { const p = LIST[0].make(); p.name = "VMAT-TBI, lungs 7.5 Gy"; p.objectives[2].dose = 7.5; return p; } },
    { id: "tbi-single", phantom: "rando", label: "TBI · one arc per isocentre", make: () => plan({
      name: "VMAT-TBI, single arcs", params: { maxDoseRate: 250 }, beams: tbiIsos(THESIS.map(t => [...t, 1])), objectives: tbiObj(), goals: tbiGoals() }) },
    { id: "tbi-four", phantom: "rando", label: "TBI · 4 isocentres", make: () => plan({
      name: "VMAT-TBI, 4 isocentres", params: { maxDoseRate: 250 },
      beams: tbiIsos([["A", 11.5, -11.5, 12.5], ["B", 34.5, -11.5, 11.5], ["C", 56.5, -11.5, 11.5], ["D", 78.5, -11.5, 11.5]]), objectives: tbiObj(), goals: tbiGoals() }) },
    { id: "tbi-conv", phantom: "rando", label: "TBI · conventional AP/PA, extended SSD, lung blocks", make: () => plan({
      name: "Conventional TBI, AP/PA at 400 cm", technique: "Conventional TBI", params: { maxDoseRate: 600 },
      beams: [fld("AP", iso(0, 0, 45), 0, -24, 24, -48, 48, { mlc: "blocks", blockStruct: "Lungs", blockT: 0.5, blockMargin: 1, sad: 400, standing: true }),
              fld("PA", iso(0, 0, 45), 180, -24, 24, -48, 48, { mlc: "blocks", blockStruct: "Lungs", blockT: 0.5, blockMargin: 1, sad: 400, standing: true })],
      objectives: tbiObj(), goals: tbiGoals(false) }) },
    { id: "tbi-adult", phantom: "adult", label: "TBI · adult 170 cm: VMAT HFS + AP/PA FFS legs (bias dose)", make: () => plan({
      name: "TBI adult, HFS VMAT + FFS legs", params: { maxDoseRate: 600 },
      beams: [...tbiIsos([["A", 16, -16, 16], ["B", 44, -14, 14], ["C", 70, -14, 14], ["D", 96, -14, 14]]),
              fld("E-AP", iso(0, 0, 112), 0, -20, 20, -20, 20, { orient: "FFS", part: 2 }), fld("E-PA", iso(0, 0, 112), 180, -20, 20, -20, 20, { orient: "FFS", part: 2 }),
              fld("F-AP", iso(0, 0, 150), 0, -20, 20, -20, 20, { orient: "FFS", part: 2 }), fld("F-PA", iso(0, 0, 150), 180, -20, 20, -20, 20, { orient: "FFS", part: 2 })],
      objectives: tbiObj(), goals: tbiGoals(false) }) },
    { id: "tbi-child", phantom: "child", label: "TBI · child 120 cm: VMAT HFS + AP/PA FFS legs", make: () => plan({
      name: "TBI child", params: { maxDoseRate: 600 },
      beams: [...tbiIsos([["A", 12, -12, 12], ["B", 34, -12, 12], ["C", 57, -13, 13]]),
              fld("D-AP", iso(0, 0, 84), 0, -14, 14, -16, 16, { orient: "FFS", part: 2 }), fld("D-PA", iso(0, 0, 84), 180, -14, 14, -16, 16, { orient: "FFS", part: 2 }),
              fld("E-AP", iso(0, 0, 108), 0, -14, 14, -13, 13, { orient: "FFS", part: 2 }), fld("E-PA", iso(0, 0, 108), 180, -14, 14, -13, 13, { orient: "FFS", part: 2 })],
      objectives: tbiObj(), goals: tbiGoals(false) }) },

    // ---------------------------------------------------------------- general sites
    { id: "hn-vmat", phantom: "hn", label: "Head & neck · VMAT 2 arcs (70 Gy)", make: () => { const I = iso(0, -0.3, 20.5); return plan({
      name: "H&N VMAT", rx: 70, fx: 35, cpStep: 10,
      beams: [arc("Arc1", I, "CW", -10, 10, -10.5, 10.5, { coll: 15 }), arc("Arc2", I, "CCW", -10, 10, -10.5, 10.5, { coll: 345 })],
      objectives: [ob("PTV", "Target Penalty", 70, 95), ob("PTV", "Quadratic Overdose", 74, 0.5), ob("Parotid_R", "Parallel", 26, 45), ob("Parotid_L", "Parallel", 26, 45),
        ob("SpinalCord", "Serial", 38, 12, 1, true, "constraint"), ob("Brainstem", "Serial", 45, 8, 1, true, "constraint"), ob("Mandible", "Maximum Dose", 72, 0),
        ob("Body", "Conformality", 70, 2.5, 0.3), ob("Body", "Maximum Dose", 76, 0)],
      goals: [goal("PTV", "V", 66.5, ">=", 95), goal("PTV", "D", 2, "<=", 74.9), goal("Parotid_R", "Dmean", null, "<=", 26), goal("Parotid_L", "Dmean", null, "<=", 26),
        goal("SpinalCord", "Dmax", null, "<=", 45), goal("Brainstem", "Dmax", null, "<=", 54), goal("Mandible", "Dmax", null, "<=", 70), goal("PTV", "CI", null, ">=", 0.7), goal("Body", "MU", null, "", null)] }); } },
    { id: "lung-vmat", phantom: "lung", label: "Lung · VMAT partial arcs (60 Gy)", make: () => { const I = iso(-7, 0.5, 16); return plan({
      name: "Lung VMAT", rx: 60, fx: 30, cpStep: 10,
      beams: [arc("Arc1", I, "CW", -5.5, 5.5, -5.5, 5.5, { start: 181, stop: 30 }), arc("Arc2", I, "CCW", -5.5, 5.5, -5.5, 5.5, { start: 30, stop: 181, coll: 90 })],
      objectives: [ob("PTV", "Target Penalty", 60, 95), ob("PTV", "Quadratic Overdose", 64, 0.5), ob("Lungs", "Parallel", 18, 20), ob("Heart", "Parallel", 30, 15),
        ob("SpinalCord", "Serial", 38, 12, 1, true, "constraint"), ob("Esophagus", "Serial", 45, 8), ob("Body", "Conformality", 60, 2.0, 0.3)],
      goals: [goal("PTV", "V", 57, ">=", 95), goal("PTV", "D", 2, "<=", 64.2), goal("Lungs", "V", 20, "<=", 30), goal("Lungs", "Dmean", null, "<=", 20),
        goal("Heart", "Dmean", null, "<=", 20), goal("SpinalCord", "Dmax", null, "<=", 45), goal("Esophagus", "Dmean", null, "<=", 34), goal("PTV", "CI", null, ">=", 0.7), goal("Body", "MU", null, "", null)] }); } },
    { id: "lung-3d", phantom: "lung", label: "Lung · 3D-CRT 4 fields (60 Gy)", make: () => { const I = iso(-7, 0.5, 16); return plan({
      name: "Lung 3D-CRT", rx: 60, fx: 30, technique: "3D-CRT",
      beams: [fld("AP", I, 0, -6, 6, -6, 6, { mlc: "conformal", margin: 0.7 }), fld("PA", I, 180, -6, 6, -6, 6, { mlc: "conformal", margin: 0.7 }),
              fld("RAO", I, 300, -6, 6, -6, 6, { mlc: "conformal", margin: 0.7, energy: "10 MV" }), fld("RPO", I, 220, -6, 6, -6, 6, { mlc: "conformal", margin: 0.7, energy: "10 MV" })],
      objectives: [ob("PTV", "Target Penalty", 60, 95), ob("Lungs", "Parallel", 18, 20), ob("SpinalCord", "Serial", 38, 12), ob("Heart", "Parallel", 30, 15)],
      goals: [goal("PTV", "V", 57, ">=", 95), goal("PTV", "D", 2, "<=", 64.2), goal("Lungs", "V", 20, "<=", 30), goal("Lungs", "Dmean", null, "<=", 20),
        goal("SpinalCord", "Dmax", null, "<=", 45), goal("Heart", "Dmean", null, "<=", 20), goal("PTV", "CI", null, ">=", 0.6), goal("Body", "MU", null, "", null)] }); } },
    { id: "prostate-imrt", phantom: "prostate", label: "Prostate · step-and-shoot IMRT 7 fields, 10 MV (78 Gy)", make: () => { const I = iso(0, 1.0, 22); return plan({
      name: "Prostate IMRT 7F", rx: 78, fx: 39, technique: "IMRT",
      beams: [0, 52, 104, 156, 204, 256, 308].map((g, i) => fld(`F${i + 1} G${g}`, I, g, -6, 6, -5, 5, { energy: "10 MV" })),
      objectives: [ob("PTV", "Target Penalty", 78, 95), ob("PTV", "Quadratic Overdose", 81.5, 0.5, 2), ob("Rectum", "Overdose DVH", 70, 15), ob("Rectum", "Serial", 62, 8),
        ob("Bladder", "Overdose DVH", 70, 25), ob("FemHead_R", "Maximum Dose", 45, 0, 1, true, "constraint"), ob("FemHead_L", "Maximum Dose", 45, 0, 1, true, "constraint"),
        ob("Body", "Conformality", 78, 2.0, 0.3), ob("Body", "Maximum Dose", 83, 0, 1, true, "constraint")],
      goals: [goal("PTV", "V", 74.1, ">=", 95), goal("PTV", "D", 2, "<=", 83.5), goal("Rectum", "V", 70, "<=", 20), goal("Rectum", "V", 50, "<=", 50),
        goal("Bladder", "V", 70, "<=", 35), goal("FemHead_R", "Dmax", null, "<=", 50), goal("FemHead_L", "Dmax", null, "<=", 50), goal("PTV", "CI", null, ">=", 0.7), goal("Body", "MU", null, "", null)] }); } },
    { id: "prostate-vmat", phantom: "prostate", label: "Prostate · VMAT 2 arcs, 10 MV (78 Gy)", make: () => { const p = LIST.find(x => x.id === "prostate-imrt").make(), I = iso(0, 1.0, 22);
      p.name = "Prostate VMAT"; p.technique = "VMAT"; p.beams = [arc("Arc1", I, "CW", -6, 6, -5, 5, { energy: "10 MV", coll: 30 }), arc("Arc2", I, "CCW", -6, 6, -5, 5, { energy: "10 MV", coll: 330 })]; return p; } },
    { id: "breast-3d", phantom: "breast", label: "Breast · 3D-CRT tangents with wedges (50 Gy)", make: () => { const I = iso(8, -9, 20); return plan({
      name: "Left breast tangents", rx: 50, fx: 25, technique: "3D-CRT",
      beams: [fld("Med tang", I, 310, -10, 10, -10, 10, { mlc: "conformal", margin: 1.5, wedge: { angle: 15, dir: "+X" } }),
              fld("Lat tang", I, 130, -10, 10, -10, 10, { mlc: "conformal", margin: 1.5, wedge: { angle: 15, dir: "-X" } })],
      objectives: [ob("PTV", "Target Penalty", 50, 95), ob("Lung_L", "Parallel", 20, 15), ob("Heart", "Parallel", 25, 5)],
      goals: [goal("PTV", "V", 47.5, ">=", 90), goal("PTV", "D", 2, "<=", 53.5), goal("Lung_L", "V", 20, "<=", 15), goal("Heart", "Dmean", null, "<=", 4),
        goal("Breast_R", "Dmean", null, "<=", 3), goal("Body", "MU", null, "", null)] }); } },
  ];
  const byId = Object.fromEntries(LIST.map(p => [p.id, p]));
  const forPhantom = ph => LIST.filter(p => p.phantom === ph);
  return { LIST, byId, forPhantom, arc, fld, ob, goal, P0 };
})();
