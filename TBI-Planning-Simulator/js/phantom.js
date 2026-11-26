/* TBI Planning Simulator — synthetic anthropomorphic phantom (Rando-like, male, 90 cm).
 * Patient coordinates (cm): x = patient left (+), y = posterior (+), z = distance from the vertex.
 * Everything is analytic (no image data), so any slice can be sampled at any resolution.
 * This is a SYNTHETIC model for training; it is not patient data. */
"use strict";
const PH = (() => {
  const LENGTH = 90;
  // lateral (a) and AP (b) half axes of the outer contour along z
  const ZP = [0, 3, 11, 19, 22, 24, 27, 30, 40, 52, 56, 66, 72, 82, 90];
  const AX = [2, 6.5, 7.8, 6.8, 5.6, 5.5, 8.5, 15.0, 16.0, 15.5, 14.5, 14.8, 16.2, 16.6, 16.0];
  const AY = [2, 7.5, 9.5, 8.5, 5.8, 5.6, 7.0, 9.5, 10.8, 11.0, 10.4, 10.6, 10.8, 11.0, 10.5];

  function interp(z, xp, fp) {
    if (z <= xp[0]) return fp[0];
    for (let i = 1; i < xp.length; i++) {
      if (z <= xp[i]) {
        const t = (z - xp[i - 1]) / (xp[i] - xp[i - 1]);
        return fp[i - 1] + t * (fp[i] - fp[i - 1]);
      }
    }
    return fp[fp.length - 1];
  }
  function half(z) { return [interp(z, ZP, AX), interp(z, ZP, AY)]; }
  // slightly flattened posterior (lying on the couch): y is scaled down for y > 0
  function inEllipse(x, y, cx, cy, a, b) { const dx = (x - cx) / a, dy = (y - cy) / b; return dx * dx + dy * dy <= 1; }

  // lungs: two ellipsoids
  const LUNG = { zc: 41.0, hz: 12.0, cx: 7.6, cy: 0.8, a: 5.2, b: 6.6 };
  function lungs(z) {
    const t = (z - LUNG.zc) / LUNG.hz;
    if (Math.abs(t) >= 1) return [];
    const s = Math.sqrt(1 - t * t);
    // slightly larger at the base (diaphragm dome) than at the apex
    const g = s * (1 + 0.12 * t);
    return [{ name: "Lung_R", cx: -LUNG.cx, cy: LUNG.cy, a: LUNG.a * g, b: LUNG.b * g },
            { name: "Lung_L", cx: LUNG.cx, cy: LUNG.cy, a: LUNG.a * g, b: LUNG.b * g }];
  }
  // kidneys
  function kidneys(z) {
    const zc = 57, hz = 5.5, t = (z - zc) / hz;
    if (Math.abs(t) >= 1) return [];
    const s = Math.sqrt(1 - t * t);
    return [{ name: "Kidney_R", cx: -5.2, cy: 4.6, a: 2.6 * s, b: 3.2 * s },
            { name: "Kidney_L", cx: 5.2, cy: 4.6, a: 2.6 * s, b: 3.2 * s }];
  }

  function inBody(x, y, z) {
    if (z < 0 || z > LENGTH) return false;
    const [a, b] = half(z);
    return inEllipse(x, y, 0, 0, a, b);
  }
  // normalised elliptic radius (0 centre, 1 skin)
  function rho(x, y, z) { const [a, b] = half(z); return Math.sqrt((x / a) ** 2 + (y / b) ** 2); }
  function lungIndex(x, y, z, shrink = 0) {
    const L = lungs(z);
    for (let i = 0; i < L.length; i++) {
      const e = L[i];
      if (e.a > shrink && inEllipse(x, y, e.cx, e.cy, e.a - shrink, e.b - shrink)) return i + 1;
    }
    return 0;
  }
  function kidneyIndex(x, y, z) {
    const K = kidneys(z);
    for (let i = 0; i < K.length; i++) if (inEllipse(x, y, K[i].cx, K[i].cy, K[i].a, K[i].b)) return i + 1;
    return 0;
  }
  // PTV: body contracted by 3 mm, excluding lungs contracted by 2 mm (rib coverage)
  function inPTV(x, y, z) {
    if (z < 0.3 || z > LENGTH - 0.3) return false;
    const [a, b] = half(z);
    if (!inEllipse(x, y, 0, 0, a - 0.3, b - 0.3)) return false;
    return lungIndex(x, y, z, 0.2) === 0;
  }

  function bone(x, y, z) {
    const [a, b] = half(z);
    // skull shell (head)
    if (z < 21) {
      const r = rho(x, y, z);
      if (r > 0.80 && r < 0.93 && z > 1.0) return 1;
      if (z > 13 && z < 20 && Math.abs(x) < 3.5 && y < -2 && y > -6.5 && r < 0.9) return 0.6; // mandible/maxilla
    }
    // cervical spine
    if (z >= 19 && z < 28) {
      if (inEllipse(x, y, 0, b * 0.35, 1.3, 1.2)) return 1;
    }
    // thoracic / lumbar spine + spinous process
    if (z >= 28 && z < 70) {
      const cy = b * 0.45;
      if (inEllipse(x, y, 0, cy, 1.9, 1.6)) {
        if (inEllipse(x, y, 0, cy + 0.2, 0.7, 0.6)) return 0; // spinal canal
        return 1;
      }
      if (Math.abs(x) < 0.5 && y > cy + 1.6 && y < b - 1.0) return 0.8;
    }
    // ribs: thin shell inside the chest wall, one rib every 2.5 cm
    if (z > 29 && z < 56) {
      const r = rho(x, y, z);
      // ribs run obliquely: lower at the front than at the back
      const ph = (((z - 29 + 2.2 * (-y / b)) % 2.5) + 2.5) % 2.5 / 2.5;
      if (r > 0.84 && r < 0.9 && ph < 0.38 && !(Math.abs(x) < 3.0 && y < 0)) return 0.85;
      // sternum
      if (z < 50 && Math.abs(x) < 1.5 && y < -b * 0.82 && y > -b * 0.95) return 0.9;
      // scapulae
      if (z < 44 && y > b * 0.55 && Math.abs(x) > 6 && Math.abs(x) < 12 && r < 0.95 && r > 0.75) return 0.7;
    }
    // pelvis: iliac wings, sacrum, femoral heads
    if (z >= 66 && z < 82) {
      for (const s of [-1, 1]) {
        if (inEllipse(x, y, s * 10.5, b * 0.15, 3.2, 6.5) && !inEllipse(x, y, s * 10.0, b * 0.05, 2.0, 5.0)) return 0.9;
      }
      if (z < 78 && inEllipse(x, y, 0, b * 0.55, 3.0, 1.8)) return 0.9;
    }
    if (z >= 80) {
      for (const s of [-1, 1]) {
        if (inEllipse(x, y, s * 8.8, 0.5, 2.3, 2.3)) return inEllipse(x, y, s * 8.8, 0.5, 1.2, 1.2) ? 0.6 : 1;
      }
    }
    return 0;
  }

  // CT number (HU)
  function hu(x, y, z, noJoint) {
    if (!inBody(x, y, z)) return -1000;
    // Rando slice joints (2.5 cm) as very thin low-density lines (not in axial images)
    const ph = z % 2.5;
    if (!noJoint && (ph < 0.03 || ph > 2.47)) return -250;
    const bn = bone(x, y, z);
    if (bn > 0) return 200 + 900 * bn;
    if (lungIndex(x, y, z) > 0) {
      // lung parenchyma with faint vessel texture
      const v = Math.sin(x * 2.1 + z * 1.3) * Math.sin(y * 1.7 - z * 0.9);
      return -820 + 60 * v * v;
    }
    if (kidneyIndex(x, y, z) > 0) return 35;
    const r = rho(x, y, z);
    if (r > 0.92) return -90;               // subcutaneous fat layer
    // brain slightly brighter than muscle
    if (z < 19 && r < 0.8) return 32;
    return 45 + 8 * Math.sin(x * 0.9 + y * 0.7 + z * 0.3);
  }

  function density(h) { // relative electron density from HU (bilinear)
    if (h <= 0) return Math.max(0.001, 1 + h / 1000);
    return 1 + h * 0.00055;
  }

  // structure list for display and DVH
  const STRUCTS = [
    { id: "Body", color: "#7fdc7f", test: (x, y, z) => inBody(x, y, z) },
    { id: "PTV", color: "#ff4d4d", test: (x, y, z) => inPTV(x, y, z) },
    { id: "Lung_R", color: "#4fa3ff", test: (x, y, z) => lungIndex(x, y, z) === 1 },
    { id: "Lung_L", color: "#a07bff", test: (x, y, z) => lungIndex(x, y, z) === 2 },
    { id: "Lungs", color: "#4fd8ff", test: (x, y, z) => lungIndex(x, y, z) > 0, dvhOnly: true },
    { id: "Kidneys", color: "#ffd24d", test: (x, y, z) => kidneyIndex(x, y, z) > 0 },
  ];

  // cross-section polygon (for the 3D mesh and outlines)
  function ring(z, n = 48) {
    const [a, b] = half(z), pts = [];
    for (let i = 0; i < n; i++) { const t = (i / n) * Math.PI * 2; pts.push([a * Math.cos(t), b * Math.sin(t)]); }
    return pts;
  }

  return { LENGTH, half, inBody, inPTV, lungs, kidneys, lungIndex, kidneyIndex, hu, density, bone, rho, STRUCTS, ring, inEllipse };
})();
