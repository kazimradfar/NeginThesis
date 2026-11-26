/* RT Planning Simulator — library of SYNTHETIC analytic phantoms (training only, no patient data).
 * Patient coordinates (cm): x = patient left (+), y = posterior (+), z = distance from the vertex (cranial end).
 * Each phantom provides, per axial position z:
 *   body(z)   -> array of ellipses {cx, cy, a, b} (their union is the external contour)
 *   inhom(z)  -> array of heterogeneities {cx, cy, a, b, rho, cls, hole?} used by the dose engine
 *   hu(x,y,z) -> CT number for the images
 * and a list of analytic structures (rasterised into editable masks when loaded). */
"use strict";
const PHANTOMS = (() => {
  const inE = (x, y, e, s = 0) => e.a > s && e.b > s && ((x - e.cx) / (e.a - s)) ** 2 + ((y - e.cy) / (e.b - s)) ** 2 <= 1;
  const inAny = (x, y, L, s = 0) => { for (const e of L) if (inE(x, y, e, s)) return true; return false; };
  function interp(z, xp, fp) {
    if (z <= xp[0]) return fp[0];
    for (let i = 1; i < xp.length; i++) if (z <= xp[i]) { const t = (z - xp[i - 1]) / (xp[i] - xp[i - 1]); return fp[i - 1] + t * (fp[i] - fp[i - 1]); }
    return fp[fp.length - 1];
  }
  // ellipsoid cross-section at z (null outside)
  function eld(z, cx, cy, cz, a, b, c) {
    const t = (z - cz) / c; if (Math.abs(t) >= 1) return null;
    const s = Math.sqrt(1 - t * t); return { cx, cy, a: a * s, b: b * s };
  }
  const cyl = (z, z0, z1, cx, cy, a, b) => (z >= z0 && z <= z1 ? { cx, cy, a, b } : null);
  const nn = arr => arr.filter(Boolean);
  const rhoOf = (x, y, e) => Math.sqrt(((x - e.cx) / e.a) ** 2 + ((y - e.cy) / e.b) ** 2);

  // ------------------------------------------------------------------ Rando-like trunk (z 0..90)
  const RZ = [0, 3, 11, 19, 22, 24, 27, 30, 40, 52, 56, 66, 72, 82, 90];
  const RA = [2, 6.5, 7.8, 6.8, 5.6, 5.5, 8.5, 15.0, 16.0, 15.5, 14.5, 14.8, 16.2, 16.6, 16.0];
  const RB = [2, 7.5, 9.5, 8.5, 5.8, 5.6, 7.0, 9.5, 10.8, 11.0, 10.4, 10.6, 10.8, 11.0, 10.5];
  const R = {
    half: z => [interp(z, RZ, RA), interp(z, RZ, RB)],
    lungs(z) {
      const t = (z - 41) / 12; if (Math.abs(t) >= 1) return [];
      const g = Math.sqrt(1 - t * t) * (1 + 0.12 * t);
      return [{ cx: -7.6, cy: 0.8, a: 5.2 * g, b: 6.6 * g }, { cx: 7.6, cy: 0.8, a: 5.2 * g, b: 6.6 * g }];
    },
    kidneys: z => nn([eld(z, -5.2, 4.6, 57, 2.6, 3.2, 5.5), eld(z, 5.2, 4.6, 57, 2.6, 3.2, 5.5)]),
    lenses: z => nn([eld(z, -3.0, -8.4, 9.5, 0.55, 0.4, 0.45), eld(z, 3.0, -8.4, 9.5, 0.55, 0.4, 0.45)]),
    spine(z) {
      const [, b] = R.half(z);
      if (z >= 19 && z < 28) return { cx: 0, cy: b * 0.35, a: 1.3, b: 1.2 };
      if (z >= 28 && z < 70) return { cx: 0, cy: b * 0.45, a: 1.9, b: 1.6 };
      return null;
    },
    bone(x, y, z) {
      const [a, b] = R.half(z), E = { cx: 0, cy: 0, a, b }, r = rhoOf(x, y, E);
      if (z < 21 && r > 0.80 && r < 0.93 && z > 1.0) return 1;
      if (z > 13 && z < 20 && Math.abs(x) < 3.5 && y < -2 && y > -6.5 && r < 0.9) return 0.6;
      const sp = R.spine(z);
      if (sp && inE(x, y, sp)) return inE(x, y, { cx: 0, cy: sp.cy + 0.2, a: 0.7, b: 0.6 }) ? 0 : 1;
      if (z >= 28 && z < 70 && Math.abs(x) < 0.5 && sp && y > sp.cy + 1.6 && y < b - 1.0) return 0.8;
      if (z > 29 && z < 56) {
        const ph = (((z - 29 + 2.2 * (-y / b)) % 2.5) + 2.5) % 2.5 / 2.5;
        if (r > 0.84 && r < 0.9 && ph < 0.38 && !(Math.abs(x) < 3.0 && y < 0)) return 0.85;
        if (z < 50 && Math.abs(x) < 1.5 && y < -b * 0.82 && y > -b * 0.95) return 0.9;
        if (z < 44 && y > b * 0.55 && Math.abs(x) > 6 && Math.abs(x) < 12 && r < 0.95 && r > 0.75) return 0.7;
      }
      if (z >= 66 && z < 82) {
        for (const s of [-1, 1]) if (inE(x, y, { cx: s * 10.5, cy: b * 0.15, a: 3.2, b: 6.5 }) && !inE(x, y, { cx: s * 10, cy: b * 0.05, a: 2, b: 5 })) return 0.9;
        if (z < 78 && inE(x, y, { cx: 0, cy: b * 0.55, a: 3.0, b: 1.8 })) return 0.9;
      }
      if (z >= 80) for (const s of [-1, 1]) if (inE(x, y, { cx: s * 8.8, cy: 0.5, a: 2.3, b: 2.3 })) return inE(x, y, { cx: s * 8.8, cy: 0.5, a: 1.2, b: 1.2 }) ? 0.6 : 1;
      return 0;
    },
  };

  // generic TBI body: trunk from the Rando model (scaled), optional legs
  function tbiBody(o) {
    const sz = o.trunk / 90, sx = o.wide;
    const legsZ0 = o.trunk - 4 * sz;
    function trunk(z) {
      if (z > o.trunk || z < 0) return null;
      const [a, b] = R.half(z / sz); return { cx: 0, cy: 0, a: a * sx, b: b * sx };
    }
    function legs(z) {
      if (!o.legs || z < legsZ0 || z > o.length) return [];
      const t = (z - legsZ0) / (o.length - legsZ0);
      const cx = (9.2 - 2.4 * t) * sx, a = (8.2 - 4.0 * t) * sx * (z > o.length - 6 ? 0.85 : 1), b = (8.6 - 4.1 * t) * sx;
      const feet = z > o.length - 6 ? 2.5 * sx : 0;
      return [{ cx: -cx, cy: -feet * 0.5, a, b: b + feet * 0.5 }, { cx, cy: -feet * 0.5, a, b: b + feet * 0.5 }];
    }
    function body(z) {
      const L = []; const t = trunk(z);
      if (t && !(o.legs && z > o.trunk - 1)) L.push(t);
      L.push(...legs(z));
      return L;
    }
    const sc = e => ({ cx: e.cx * sx, cy: e.cy * sx, a: e.a * sx, b: e.b * sx });
    const lungs = z => R.lungs(z / sz).map(sc);
    const kidneys = z => R.kidneys(z / sz).map(sc);
    const lenses = z => R.lenses(z / sz).map(sc);
    function inhom(z, dens) {
      const out = lungs(z).map(e => ({ ...e, rho: dens.lung, cls: "lung" }));
      if (z < o.trunk) {
        const sp = R.spine(z / sz); if (sp) out.push({ ...sc(sp), rho: dens.bone, cls: "bone" });
        if (z / sz < 21 && z / sz > 2) { const [a, b] = R.half(z / sz); out.push({ cx: 0, cy: 0, a: a * sx * 0.93, b: b * sx * 0.93, rho: dens.bone, cls: "bone", hole: { a: a * sx * 0.8, b: b * sx * 0.8 } }); }
      }
      if (o.legs && z > o.trunk) for (const e of legs(z)) out.push({ cx: e.cx * 0.95, cy: e.cy + 0.3, a: 1.4 * sx, b: 1.4 * sx, rho: dens.bone, cls: "bone" });
      return out;
    }
    function hu(x, y, z, noJoint) {
      const B = body(z); if (!inAny(x, y, B)) return -1000;
      if (o.joints && !noJoint) { const ph = z % 2.5; if (ph < 0.03 || ph > 2.47) return -250; }
      if (z <= o.trunk && B[0] && B[0].cx === 0 && inE(x, y, B[0])) {
        const zr = z / sz, xr = x / sx, yr = y / sx;
        const bn = R.bone(xr, yr, zr); if (bn > 0) return 200 + 900 * bn;
        for (const e of lungs(z)) if (inE(x, y, e)) { const v = Math.sin(x * 2.1 + z * 1.3) * Math.sin(y * 1.7 - z * 0.9); return -820 + 60 * v * v; }
        for (const e of kidneys(z)) if (inE(x, y, e)) return 35;
        for (const e of lenses(z)) if (inE(x, y, e)) return 70;
        const r = rhoOf(x, y, B[0]); if (r > 0.92) return -90;
        if (zr < 19 && r < 0.8) return 32;
        return 45 + 8 * Math.sin(x * 0.9 + y * 0.7 + z * 0.3);
      }
      for (const e of legs(z)) if (inE(x, y, e)) {
        const bone = { cx: e.cx * 0.95, cy: e.cy + 0.3, a: 1.4 * sx, b: 1.4 * sx };
        if (inE(x, y, bone)) return inE(x, y, { ...bone, a: bone.a * 0.55, b: bone.b * 0.55 }) ? 300 : 1100;
        return rhoOf(x, y, e) > 0.9 ? -90 : 48;
      }
      return 45;
    }
    return { body, inhom, hu, lungs, kidneys, lenses, trunk };
  }

  function ptvTest(G, shrinkBody = 0.3, lungMargin = 0.2) {
    return (x, y, z) => {
      const B = G.body(z); if (!inAny(x, y, B, shrinkBody)) return false;
      for (const e of G.lungs(z)) if (inE(x, y, e, lungMargin)) return false;
      return true;
    };
  }

  function makeTBI(id, name, desc, o, plan) {
    const G = tbiBody(o);
    const structs = [
      { id: "Body", color: "#7fdc7f", role: "body", test: (x, y, z) => inAny(x, y, G.body(z)) },
      { id: "PTV", color: "#ff4d4d", role: "target", test: ptvTest(G) },
      { id: "Lung_R", color: "#4fa3ff", role: "oar", test: (x, y, z) => { const L = G.lungs(z); return L.length > 0 && inE(x, y, L[0]); } },
      { id: "Lung_L", color: "#a07bff", role: "oar", test: (x, y, z) => { const L = G.lungs(z); return L.length > 1 && inE(x, y, L[1]); } },
      { id: "Kidneys", color: "#ffd24d", role: "oar", test: (x, y, z) => inAny(x, y, G.kidneys(z)) },
      { id: "Lenses", color: "#ff9ff3", role: "oar", test: (x, y, z) => inAny(x, y, G.lenses(z)) },
    ];
    const W = 18 * o.wide + (o.legs ? 2 : 0);
    return { id, name, desc, kind: "tbi", z0: 0, z1: o.length, xr: [-W, W], yr: [-12.5 * o.wide, 12.5 * o.wide],
      body: G.body, inhom: G.inhom, hu: G.hu, structs, joints: !!o.joints, groups: { Lungs: ["Lung_R", "Lung_L"] },
      lungs: G.lungs, cross: { x: 0, y: 0.8 * o.wide, z: 41 * o.trunk / 90 }, plan, grid: o.grid };
  }

  // ------------------------------------------------------------------ site phantoms
  function makeSite(cfg) {
    const body = z => cfg.body(z);
    const structs = cfg.structs;
    function hu(x, y, z) {
      const B = body(z); if (!inAny(x, y, B)) return -1000;
      for (const h of cfg.inhom(z, { lung: 0.25, bone: 1.6, air: 0.001 })) {
        if (inE(x, y, h) && !(h.hole && inE(x, y, { cx: h.cx, cy: h.cy, a: h.hole.a, b: h.hole.b }))) {
          if (h.cls === "lung") { const v = Math.sin(x * 2.1 + z * 1.3) * Math.sin(y * 1.7 - z * 0.9); return -820 + 60 * v * v; }
          if (h.cls === "bone") return 1050;
          if (h.cls === "air") return -980;
        }
      }
      if (cfg.huExtra) { const v = cfg.huExtra(x, y, z); if (v !== null) return v; }
      let edge = 1e9; for (const e of B) edge = Math.min(edge, Math.abs(1 - rhoOf(x, y, e)) * Math.min(e.a, e.b));
      if (edge < 1.0) return -90;
      return 42 + 6 * Math.sin(x * 0.8 + y * 0.6 + z * 0.4);
    }
    return { kind: "site", joints: false, groups: cfg.groups || {}, lungs: cfg.lungs || (() => []), hu, body, ...cfg };
  }

  // head & neck (vertex 0 .. upper chest 40)
  const HN_Z = [0, 3, 10, 18, 21, 24, 27, 31, 40], HN_A = [2, 6.6, 7.8, 6.9, 5.7, 5.6, 8.5, 15, 16], HN_B = [2, 7.6, 9.5, 8.6, 5.9, 5.7, 7.2, 9.5, 10.5];
  const hnHalf = z => ({ cx: 0, cy: 0, a: interp(z, HN_Z, HN_A), b: interp(z, HN_Z, HN_B) });
  const HN = makeSite({
    id: "hn", name: "Head & neck (synthetic)", desc: "Oropharynx target with bilateral neck nodes", z0: 0, z1: 40, xr: [-18, 18], yr: [-12, 12],
    body: z => (z >= 0 && z <= 40 ? [hnHalf(z)] : []),
    inhom: (z, d) => nn([
      z > 1 && z < 19 ? { ...hnHalf(z), a: hnHalf(z).a * 0.93, b: hnHalf(z).b * 0.93, rho: d.bone, cls: "bone", hole: { a: hnHalf(z).a * 0.8, b: hnHalf(z).b * 0.8 } } : null,
      z >= 15 && z <= 34 ? { cx: 0, cy: -1.2, a: 0.9, b: 0.8, rho: d.air, cls: "air" } : null,
      z >= 17 && z <= 40 ? { cx: 0, cy: 3.6, a: 1.3, b: 1.2, rho: d.bone, cls: "bone" } : null,
      z >= 13 && z <= 19 ? { cx: 0, cy: -5.0, a: 4.2, b: 1.0, rho: d.bone, cls: "bone" } : null,
    ]),
    structs: [
      { id: "Body", color: "#7fdc7f", role: "body", test: (x, y, z) => z >= 0 && z <= 40 && inE(x, y, hnHalf(z)) },
      { id: "PTV", color: "#ff4d4d", role: "target", test: (x, y, z) => inAny(x, y, nn([eld(z, 0, -0.5, 17, 3.8, 3.2, 4.5), eld(z, -3.6, 0.6, 24, 1.9, 2.0, 5.0), eld(z, 3.6, 0.6, 24, 1.9, 2.0, 5.0)])) && inE(x, y, hnHalf(z), 0.5) },
      { id: "Parotid_R", color: "#4fa3ff", role: "oar", test: (x, y, z) => { const e = eld(z, -5.2, 0.8, 15.5, 1.7, 2.3, 2.6); return !!e && inE(x, y, e); } },
      { id: "Parotid_L", color: "#a07bff", role: "oar", test: (x, y, z) => { const e = eld(z, 5.2, 0.8, 15.5, 1.7, 2.3, 2.6); return !!e && inE(x, y, e); } },
      { id: "SpinalCord", color: "#ffd24d", role: "oar", test: (x, y, z) => z >= 12 && z <= 40 && inE(x, y, { cx: 0, cy: 3.7, a: 0.55, b: 0.5 }) },
      { id: "Brainstem", color: "#ff9f43", role: "oar", test: (x, y, z) => { const e = eld(z, 0, 2.0, 9.5, 1.3, 1.3, 2.8); return !!e && inE(x, y, e); } },
      { id: "Mandible", color: "#c8d6e5", role: "oar", test: (x, y, z) => z >= 13 && z <= 19 && inE(x, y, { cx: 0, cy: -5.0, a: 4.2, b: 1.0 }) },
    ],
    cross: { x: 0, y: 0, z: 17 }, grid: 0.6,
  });

  // lung (thorax 0..45, tumour in the right lung)
  const LZ = [0, 6, 12, 30, 40, 45], LA = [6, 14.5, 15.5, 15.5, 15.0, 14.8], LB = [6, 9.2, 10.5, 10.8, 10.6, 10.5];
  const lHalf = z => ({ cx: 0, cy: 0, a: interp(z, LZ, LA), b: interp(z, LZ, LB) });
  const lLungs = z => { const t = (z - 20) / 14; if (Math.abs(t) >= 1) return []; const g = Math.sqrt(1 - t * t) * (1 + 0.1 * t); return [{ cx: -7.4, cy: 0.8, a: 5.2 * g, b: 6.6 * g }, { cx: 7.4, cy: 0.8, a: 5.2 * g, b: 6.6 * g }]; };
  const LUNG = makeSite({
    id: "lung", name: "Lung (synthetic)", desc: "Right upper-lobe tumour", z0: 0, z1: 45, xr: [-18, 18], yr: [-12, 12],
    body: z => (z >= 0 && z <= 45 ? [lHalf(z)] : []), lungs: lLungs,
    inhom: (z, d) => [...lLungs(z).map(e => ({ ...e, rho: d.lung, cls: "lung" })), { cx: 0, cy: 5.0, a: 1.9, b: 1.6, rho: d.bone, cls: "bone" }],
    huExtra: (x, y, z) => { const e = eld(z, -7.0, 0.5, 16, 1.6, 1.6, 1.8); if (e && inE(x, y, e)) return 30; return null; },
    structs: [
      { id: "Body", color: "#7fdc7f", role: "body", test: (x, y, z) => z >= 0 && z <= 45 && inE(x, y, lHalf(z)) },
      { id: "GTV", color: "#ff2d55", role: "target", test: (x, y, z) => { const e = eld(z, -7.0, 0.5, 16, 1.6, 1.6, 1.8); return !!e && inE(x, y, e); } },
      { id: "PTV", color: "#ff4d4d", role: "target", test: (x, y, z) => { const e = eld(z, -7.0, 0.5, 16, 2.6, 2.6, 2.8); return !!e && inE(x, y, e); } },
      { id: "Lung_R", color: "#4fa3ff", role: "oar", test: (x, y, z) => { const L = lLungs(z); return L.length > 0 && inE(x, y, L[0]); } },
      { id: "Lung_L", color: "#a07bff", role: "oar", test: (x, y, z) => { const L = lLungs(z); return L.length > 1 && inE(x, y, L[1]); } },
      { id: "Heart", color: "#ff9ff3", role: "oar", test: (x, y, z) => { const e = eld(z, 2.6, -2.2, 27, 5.0, 4.4, 6.0); return !!e && inE(x, y, e); } },
      { id: "Esophagus", color: "#ff9f43", role: "oar", test: (x, y, z) => z >= 4 && z <= 38 && inE(x, y, { cx: 0.6, cy: 2.6, a: 0.9, b: 0.8 }) },
      { id: "SpinalCord", color: "#ffd24d", role: "oar", test: (x, y, z) => inE(x, y, { cx: 0, cy: 5.2, a: 0.6, b: 0.55 }) },
    ],
    groups: { Lungs: ["Lung_R", "Lung_L"] }, cross: { x: -7, y: 0.5, z: 16 }, grid: 0.6,
  });

  // prostate (pelvis 0..40)
  const pHalf = z => ({ cx: 0, cy: 0, a: interp(z, [0, 10, 25, 40], [15.5, 16.5, 17.5, 16.5]), b: interp(z, [0, 10, 25, 40], [10.4, 10.8, 11.2, 10.6]) });
  const PROST = makeSite({
    id: "prostate", name: "Prostate (synthetic)", desc: "Prostate with rectum and bladder", z0: 0, z1: 40, xr: [-19, 19], yr: [-12.5, 12.5],
    body: z => (z >= 0 && z <= 40 ? [pHalf(z)] : []),
    inhom: (z, d) => nn([
      cyl(z, 20, 40, -9.2, 0.5, 2.3, 2.3) && { cx: -9.2, cy: 0.5, a: 2.3, b: 2.3, rho: d.bone, cls: "bone" },
      cyl(z, 20, 40, 9.2, 0.5, 2.3, 2.3) && { cx: 9.2, cy: 0.5, a: 2.3, b: 2.3, rho: d.bone, cls: "bone" },
      z < 20 ? { cx: -10.5, cy: 1.5, a: 3.0, b: 6.0, rho: d.bone, cls: "bone", hole: { a: 1.8, b: 4.6 } } : null,
      z < 20 ? { cx: 10.5, cy: 1.5, a: 3.0, b: 6.0, rho: d.bone, cls: "bone", hole: { a: 1.8, b: 4.6 } } : null,
      z < 24 ? { cx: 0, cy: 7.5, a: 2.6, b: 1.6, rho: d.bone, cls: "bone" } : null,
    ]),
    huExtra: (x, y, z) => { const e = eld(z, 0, -1.5, 16, 4.2, 3.6, 3.2); if (e && inE(x, y, e)) return 8; if (z > 14 && z < 34 && inE(x, y, { cx: 0, cy: 4.4, a: 1.4, b: 1.3 })) return inE(x, y, { cx: 0, cy: 4.4, a: 0.6, b: 0.5 }) ? -600 : 30; return null; },
    structs: [
      { id: "Body", color: "#7fdc7f", role: "body", test: (x, y, z) => z >= 0 && z <= 40 && inE(x, y, pHalf(z)) },
      { id: "Prostate", color: "#ff2d55", role: "target", test: (x, y, z) => { const e = eld(z, 0, 1.0, 22, 2.3, 1.9, 2.3); return !!e && inE(x, y, e); } },
      { id: "PTV", color: "#ff4d4d", role: "target", test: (x, y, z) => { const e = eld(z, 0, 1.0, 22, 3.1, 2.5, 3.1); return !!e && inE(x, y, e) && !inE(x, y, { cx: 0, cy: 4.4, a: 1.4, b: 1.3 }); } },
      { id: "Rectum", color: "#c49a6c", role: "oar", test: (x, y, z) => z > 14 && z < 34 && inE(x, y, { cx: 0, cy: 4.4, a: 1.4, b: 1.3 }) },
      { id: "Bladder", color: "#ffd24d", role: "oar", test: (x, y, z) => { const e = eld(z, 0, -1.5, 16, 4.2, 3.6, 3.2); return !!e && inE(x, y, e); } },
      { id: "FemHead_R", color: "#4fa3ff", role: "oar", test: (x, y, z) => z >= 20 && z <= 26 && inE(x, y, { cx: -9.2, cy: 0.5, a: 2.3, b: 2.3 }) },
      { id: "FemHead_L", color: "#a07bff", role: "oar", test: (x, y, z) => z >= 20 && z <= 26 && inE(x, y, { cx: 9.2, cy: 0.5, a: 2.3, b: 2.3 }) },
    ],
    cross: { x: 0, y: 1, z: 22 }, grid: 0.5,
  });

  // breast (left breast on a thorax 0..40)
  const bHalf = z => ({ cx: 0, cy: 0, a: interp(z, [0, 6, 20, 40], [12, 15.5, 16, 15]), b: interp(z, [0, 6, 20, 40], [8.5, 10.2, 10.8, 10.4]) });
  const breastE = z => eld(z, 7.5, -9.2, 20, 7.0, 4.2, 9.0), breastRE = z => eld(z, -7.5, -9.2, 20, 6.6, 3.9, 8.6);
  const bLungs = z => { const t = (z - 18) / 15; if (Math.abs(t) >= 1) return []; const g = Math.sqrt(1 - t * t); return [{ cx: -7.4, cy: 0.8, a: 5.2 * g, b: 6.6 * g }, { cx: 7.4, cy: 0.8, a: 5.2 * g, b: 6.6 * g }]; };
  const BREAST = makeSite({
    id: "breast", name: "Breast (synthetic)", desc: "Left breast, tangential fields", z0: 0, z1: 40, xr: [-18, 20], yr: [-15, 12],
    body: z => (z >= 0 && z <= 40 ? nn([bHalf(z), breastE(z), breastRE(z)]) : []), lungs: bLungs,
    inhom: (z, d) => bLungs(z).map(e => ({ ...e, rho: d.lung, cls: "lung" })),
    structs: [
      { id: "Body", color: "#7fdc7f", role: "body", test: (x, y, z) => z >= 0 && z <= 40 && inAny(x, y, nn([bHalf(z), breastE(z), breastRE(z)])) },
      { id: "PTV", color: "#ff4d4d", role: "target", test: (x, y, z) => { const e = breastE(z); return !!e && inE(x, y, e, 0.5) && !inE(x, y, bHalf(z), 0); } },
      { id: "Lung_L", color: "#a07bff", role: "oar", test: (x, y, z) => { const L = bLungs(z); return L.length > 1 && inE(x, y, L[1]); } },
      { id: "Lung_R", color: "#4fa3ff", role: "oar", test: (x, y, z) => { const L = bLungs(z); return L.length > 0 && inE(x, y, L[0]); } },
      { id: "Heart", color: "#ff9ff3", role: "oar", test: (x, y, z) => { const e = eld(z, 2.8, -2.6, 25, 5.0, 4.4, 6.0); return !!e && inE(x, y, e); } },
      { id: "Breast_R", color: "#ffd24d", role: "oar", test: (x, y, z) => { const e = breastRE(z); return !!e && inE(x, y, e) && !inE(x, y, bHalf(z), 0); } },
    ],
    groups: { Lungs: ["Lung_R", "Lung_L"] }, cross: { x: 7.5, y: -6, z: 20 }, grid: 0.6,
  });

  const RANDO = makeTBI("rando", "Rando-like TBI phantom (90 cm)", "Head to upper thigh, 2.5 cm slices, as in the thesis",
    { trunk: 90, length: 90, wide: 1, legs: false, joints: true, grid: 1.0 }, "tbi3");
  const ADULT = makeTBI("adult", "Adult TBI with legs (170 cm)", "Whole body; head-first plan + feet-first plan with bias dose",
    { trunk: 92, length: 170, wide: 1.03, legs: true, joints: false, grid: 1.5 }, "tbiHfsFfs");
  const CHILD = makeTBI("child", "Child TBI (120 cm)", "Paediatric whole body",
    { trunk: 62, length: 120, wide: 0.66, legs: true, joints: false, grid: 1.0 }, "tbiChild");
  RANDO.cross = { x: 0, y: 0.8, z: 42.5 };

  const LIST = [RANDO, ADULT, CHILD, HN, LUNG, PROST, BREAST];
  const byId = Object.fromEntries(LIST.map(p => [p.id, p]));
  return { LIST, byId, inE, inAny, eld };
})();
