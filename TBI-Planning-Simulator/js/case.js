/* RT Planning Simulator — the loaded case: structure masks (editable), density grid, contouring tools.
 * Masks live on a regular voxel grid (sg); each voxel holds a bit mask (one bit per structure, max 31). */
"use strict";
const CASE = (() => {
  const C = { ph: null, sg: null, structs: [], groups: {}, dens: null, dens0: null, bbox: null, version: 0, back: 11, layering: false };
  const MAXS = 31;

  function huToRho(hu) { return hu <= 0 ? Math.max(0.001, 1 + hu / 1000) : 1 + 0.6 * hu / 1000; }

  function load(id) {
    const ph = PHANTOMS.byId[id]; C.ph = ph;
    const h = ph.sgrid || (ph.kind === "tbi" ? (ph.z1 > 130 ? 0.8 : ph.z1 > 95 ? 0.6 : 0.5) : 0.4);
    const x0 = ph.xr[0], y0 = ph.yr[0], z0 = ph.z0;
    const nx = Math.ceil((ph.xr[1] - x0) / h), ny = Math.ceil((ph.yr[1] - y0) / h), nz = Math.ceil((ph.z1 - z0) / h);
    const sg = { h, x0, y0, z0, nx, ny, nz, n: nx * ny * nz };
    sg.bits = new Uint32Array(sg.n);
    C.sg = sg;
    C.structs = ph.structs.map((s, b) => ({ id: s.id, color: s.color, role: s.role, bit: 1 << b, visible: true, rho: null, user: false }));
    C.groups = {};
    for (const g in ph.groups) C.groups[g] = { id: g, members: ph.groups[g], color: "#4fd8ff" };
    const tests = ph.structs.map(s => s.test);
    const dens = new Float32Array(sg.n);
    let q = 0, back = 0;
    for (let k = 0; k < nz; k++) {
      const z = z0 + (k + 0.5) * h;
      for (let j = 0; j < ny; j++) {
        const y = y0 + (j + 0.5) * h;
        for (let i = 0; i < nx; i++, q++) {
          const x = x0 + (i + 0.5) * h;
          if (!tests[0](x, y, z)) continue;
          let b = 1;
          for (let t = 1; t < tests.length; t++) if (tests[t](x, y, z)) b |= 1 << t;
          sg.bits[q] = b;
          dens[q] = huToRho(ph.hu(x, y, z, true));
          if (y > back) back = y;
        }
      }
    }
    C.dens0 = dens; C.back = back + h / 2;
    applyDensity();
    C.version++;
    return C;
  }

  // density overrides: the structure highest in the list wins where structures overlap
  function applyDensity() {
    const sg = C.sg, d = new Float32Array(C.dens0);
    for (let s = C.structs.length - 1; s >= 0; s--) {
      const st = C.structs[s]; if (st.rho === null || st.rho === undefined || st.rho === "") continue;
      for (let q = 0; q < sg.n; q++) if (sg.bits[q] & st.bit) d[q] = +st.rho;
    }
    C.dens = d;
    // per-slice bounding boxes of the patient (to clip rays)
    C.bbox = [];
    for (let k = 0; k < sg.nz; k++) {
      let i0 = 1e9, i1 = -1, j0 = 1e9, j1 = -1;
      const base = k * sg.nx * sg.ny;
      for (let j = 0; j < sg.ny; j++) for (let i = 0; i < sg.nx; i++) if (d[base + j * sg.nx + i] > 0.01) {
        if (i < i0) i0 = i; if (i > i1) i1 = i; if (j < j0) j0 = j; if (j > j1) j1 = j;
      }
      C.bbox.push(i1 < 0 ? null : [sg.x0 + i0 * sg.h, sg.x0 + (i1 + 1) * sg.h, sg.y0 + j0 * sg.h, sg.y0 + (j1 + 1) * sg.h]);
    }
    C.densVersion = (C.densVersion || 0) + 1;
  }

  // water-equivalent depth from (x, y, z) towards the source (sx, sy) in the axial plane; -1 outside
  function radDepth(x, y, z, sx, sy) {
    const sg = C.sg, h = sg.h, k = Math.floor((z - sg.z0) / h);
    if (k < 0 || k >= sg.nz) return -1;
    const bb = C.bbox[k]; if (!bb) return -1;
    let dx = sx - x, dy = sy - y; const L = Math.hypot(dx, dy); dx /= L; dy /= L;
    // clip to the slice bounding box (inside the voxel grid), so no bounds checks are needed below
    const tx = dx > 0 ? (bb[1] - x) / dx : dx < 0 ? (bb[0] - x) / dx : 1e9;
    const ty = dy > 0 ? (bb[3] - y) / dy : dy < 0 ? (bb[2] - y) / dy : 1e9;
    const tmax = Math.min(tx, ty, L);
    if (tmax <= 0) return 0;
    const n = Math.ceil(tmax / h) - 1, base = k * sg.nx * sg.ny, D = C.dens, nx = sg.nx;
    if (x < bb[0] || x > bb[1] || y < bb[2] || y > bb[3]) return 0;
    let px = (x - sg.x0) / h + 0.5 * dx, py = (y - sg.y0) / h + 0.5 * dy, sum = 0;
    for (let s = 0; s < n; s++) { sum += D[base + (py | 0) * nx + (px | 0)]; px += dx; py += dy; }
    return sum * h;
  }

  const sgIndex = (x, y, z) => {
    const sg = C.sg, i = Math.floor((x - sg.x0) / sg.h), j = Math.floor((y - sg.y0) / sg.h), k = Math.floor((z - sg.z0) / sg.h);
    if (i < 0 || j < 0 || k < 0 || i >= sg.nx || j >= sg.ny || k >= sg.nz) return -1;
    return (k * sg.ny + j) * sg.nx + i;
  };
  function bitsAt(x, y, z) { const q = sgIndex(x, y, z); return q < 0 ? 0 : C.sg.bits[q]; }
  function rhoAt(x, y, z) { const q = sgIndex(x, y, z); return q < 0 ? 0 : C.dens[q]; }

  function find(name) { return C.structs.find(s => s.id === name); }
  function maskOf(name) {
    const s = find(name); if (s) return s.bit;
    const g = C.groups[name]; if (!g) return 0;
    let m = 0; for (const id of g.members) { const t = find(id); if (t) m |= t.bit; } return m;
  }
  function names(withGroups = true) { return [...C.structs.map(s => s.id), ...(withGroups ? Object.keys(C.groups) : [])]; }
  function colorOf(name) { const s = find(name); return s ? s.color : C.groups[name] ? C.groups[name].color : "#ccc"; }
  function volume(name) { const m = maskOf(name); let c = 0; const b = C.sg.bits; for (let q = 0; q < b.length; q++) if (b[q] & m) c++; return c * C.sg.h ** 3; }
  function targets() { return C.structs.filter(s => s.role === "target").map(s => s.id); }

  // ---------------------------------------------------------------- contouring tools
  const PALETTE = ["#00e5ff", "#ff6bd6", "#b8ff5c", "#ffb84d", "#9d8cff", "#5cffb1", "#ff5c5c", "#e0e0e0"];
  function newStruct(id, role = "oar", color) {
    if (C.structs.length >= MAXS) throw new Error("At most 31 structures");
    if (find(id) || C.groups[id]) throw new Error("Name already used");
    let bit = 0; for (let b = 0; b < MAXS; b++) if (!C.structs.some(s => s.bit === 1 << b)) { bit = 1 << b; break; }
    const s = { id, role, color: color || PALETTE[C.structs.length % PALETTE.length], bit, visible: true, rho: null, user: true };
    C.structs.push(s); C.version++; return s;
  }
  function removeStruct(id) {
    const s = find(id); if (!s || s.role === "body") return;
    const b = C.sg.bits; for (let q = 0; q < b.length; q++) b[q] &= ~s.bit;
    C.structs.splice(C.structs.indexOf(s), 1); C.version++;
    if (s.rho !== null) applyDensity();
  }
  // paint a disc of radius r (cm) on the slice through (x, y, z) of the given view
  function brush(id, view, x, y, z, r, erase) {
    const s = find(id); if (!s) return;
    const sg = C.sg, h = sg.h, body = C.structs[0].bit, b = sg.bits;
    const ci = Math.floor((x - sg.x0) / h), cj = Math.floor((y - sg.y0) / h), ck = Math.floor((z - sg.z0) / h);
    const R = Math.ceil(r / h);
    for (let a = -R; a <= R; a++) for (let c = -R; c <= R; c++) {
      if ((a * a + c * c) * h * h > r * r) continue;
      let i = ci, j = cj, k = ck;
      if (view === "axial") { i += a; j += c; } else if (view === "coronal") { i += a; k += c; } else { j += a; k += c; }
      if (i < 0 || j < 0 || k < 0 || i >= sg.nx || j >= sg.ny || k >= sg.nz) continue;
      const q = (k * sg.ny + j) * sg.nx + i;
      if (erase) b[q] &= ~s.bit; else if (b[q] & body || s.role === "body") b[q] |= s.bit;
    }
    C.version++;
  }
  // 3D margin (cm, negative = contract), result written into structure `dst`
  function margin(src, dst, m) {
    const sm = maskOf(src), d = find(dst); if (!sm || !d) return;
    const sg = C.sg, h = sg.h, b = sg.bits, R = Math.ceil(Math.abs(m) / h), out = new Uint8Array(sg.n);
    const offs = [];
    for (let c = -R; c <= R; c++) for (let bb = -R; bb <= R; bb++) for (let a = -R; a <= R; a++) if ((a * a + bb * bb + c * c) * h * h <= m * m + 1e-6) offs.push([a, bb, c]);
    const inS = (i, j, k) => i >= 0 && j >= 0 && k >= 0 && i < sg.nx && j < sg.ny && k < sg.nz && (b[(k * sg.ny + j) * sg.nx + i] & sm);
    for (let k = 0, q = 0; k < sg.nz; k++) for (let j = 0; j < sg.ny; j++) for (let i = 0; i < sg.nx; i++, q++) {
      const v = (b[q] & sm) !== 0;
      if (m >= 0) {
        if (!v) continue;
        // only surface voxels need to spread
        if (inS(i + 1, j, k) && inS(i - 1, j, k) && inS(i, j + 1, k) && inS(i, j - 1, k) && inS(i, j, k + 1) && inS(i, j, k - 1)) { out[q] = 1; continue; }
        for (const [a, bb, c] of offs) { const I = i + a, J = j + bb, K = k + c; if (I >= 0 && J >= 0 && K >= 0 && I < sg.nx && J < sg.ny && K < sg.nz) out[(K * sg.ny + J) * sg.nx + I] = 1; }
      } else {
        if (!v) continue;
        let keep = true; for (const [a, bb, c] of offs) if (!inS(i + a, j + bb, k + c)) { keep = false; break; }
        if (keep) out[q] = 1;
      }
    }
    const body = C.structs[0].bit;
    for (let q = 0; q < sg.n; q++) { b[q] &= ~d.bit; if (out[q] && (b[q] & body)) b[q] |= d.bit; }
    C.version++;
  }
  function boolean(a, op, bName, dst) {
    const ma = maskOf(a), mb = maskOf(bName), d = find(dst); if (!ma || !d) return;
    const b = C.sg.bits;
    for (let q = 0; q < b.length; q++) {
      const A = (b[q] & ma) !== 0, B = (b[q] & mb) !== 0;
      const r = op === "union" ? A || B : op === "intersect" ? A && B : op === "subtract" ? A && !B : A !== B;
      if (r) b[q] |= d.bit; else b[q] &= ~d.bit;
    }
    C.version++;
  }
  // shape-based interpolation between contoured axial slices (signed 2D distance per slice)
  function interpolate(id) {
    const s = find(id); if (!s) return 0;
    const sg = C.sg, b = sg.bits, nxy = sg.nx * sg.ny, slices = [];
    for (let k = 0; k < sg.nz; k++) { let any = false; for (let p = 0; p < nxy; p++) if (b[k * nxy + p] & s.bit) { any = true; break; } if (any) slices.push(k); }
    let filled = 0;
    const sdf = k => {
      const inside = new Uint8Array(nxy); for (let p = 0; p < nxy; p++) inside[p] = b[k * nxy + p] & s.bit ? 1 : 0;
      const dIn = chamfer(inside, sg.nx, sg.ny, 0), dOut = chamfer(inside, sg.nx, sg.ny, 1), out = new Float32Array(nxy);
      for (let p = 0; p < nxy; p++) out[p] = inside[p] ? -dOut[p] : dIn[p];
      return out;
    };
    const body = C.structs[0].bit;
    for (let t = 0; t < slices.length - 1; t++) {
      const k0 = slices[t], k1 = slices[t + 1]; if (k1 - k0 < 2) continue;
      const A = sdf(k0), B = sdf(k1);
      for (let k = k0 + 1; k < k1; k++) {
        const f = (k - k0) / (k1 - k0);
        for (let p = 0; p < nxy; p++) if (A[p] * (1 - f) + B[p] * f <= 0 && b[k * nxy + p] & body) { b[k * nxy + p] |= s.bit; filled++; }
      }
    }
    C.version++;
    return filled;
  }
  // 2D chamfer distance (in voxels) to the nearest voxel with mask value == target
  function chamfer(mask, nx, ny, target) {
    const INF = 1e9, d = new Float32Array(nx * ny);
    for (let p = 0; p < d.length; p++) d[p] = mask[p] === target ? 0 : INF;
    const a = 1, c = 1.4142;
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      const p = j * nx + i; let v = d[p];
      if (i > 0) v = Math.min(v, d[p - 1] + a);
      if (j > 0) { v = Math.min(v, d[p - nx] + a); if (i > 0) v = Math.min(v, d[p - nx - 1] + c); if (i < nx - 1) v = Math.min(v, d[p - nx + 1] + c); }
      d[p] = v;
    }
    for (let j = ny - 1; j >= 0; j--) for (let i = nx - 1; i >= 0; i--) {
      const p = j * nx + i; let v = d[p];
      if (i < nx - 1) v = Math.min(v, d[p + 1] + a);
      if (j < ny - 1) { v = Math.min(v, d[p + nx] + a); if (i < nx - 1) v = Math.min(v, d[p + nx + 1] + c); if (i > 0) v = Math.min(v, d[p + nx - 1] + c); }
      d[p] = v;
    }
    return d;
  }
  function clearStruct(id) { const s = find(id); if (!s) return; const b = C.sg.bits; for (let q = 0; q < b.length; q++) b[q] &= ~s.bit; C.version++; }

  // mask slice for display: values 0/1 sampled on the view's native grid
  function maskSlice(name, view, X) {
    const sg = C.sg, m = maskOf(name), h = sg.h;
    let nu, nv, u0, v0, get;
    if (view === "axial") {
      const k = Math.floor((X.z - sg.z0) / h); nu = sg.nx; nv = sg.ny; u0 = sg.x0; v0 = sg.y0;
      get = (i, j) => k >= 0 && k < sg.nz ? sg.bits[(k * sg.ny + j) * sg.nx + i] : 0;
    } else if (view === "coronal") {
      const j = Math.floor((X.y - sg.y0) / h); nu = sg.nx; nv = sg.nz; u0 = sg.x0; v0 = sg.z0;
      get = (i, k) => j >= 0 && j < sg.ny ? sg.bits[(k * sg.ny + j) * sg.nx + i] : 0;
    } else {
      const i = Math.floor((X.x - sg.x0) / h); nu = sg.ny; nv = sg.nz; u0 = sg.y0; v0 = sg.z0;
      get = (j, k) => i >= 0 && i < sg.nx ? sg.bits[(k * sg.ny + j) * sg.nx + i] : 0;
    }
    // padded by one voxel and lightly blurred for smooth contours
    const W = nu + 2, H = nv + 2, raw = new Float32Array(W * H), out = new Float32Array(W * H);
    for (let b = 0; b < nv; b++) for (let a = 0; a < nu; a++) raw[(b + 1) * W + a + 1] = get(a, b) & m ? 1 : 0;
    for (let b = 1; b < H - 1; b++) for (let a = 1; a < W - 1; a++) {
      const p = b * W + a;
      out[p] = (4 * raw[p] + raw[p - 1] + raw[p + 1] + raw[p - W] + raw[p + W]) / 8;
    }
    return { vals: out, nx: W, ny: H, x0: u0 - h / 2, y0: v0 - h / 2, h };
  }

  // structure set in plan files: order, roles, density overrides and the masks of user-made structures (run-length coded)
  function exportStructs() {
    const b = C.sg.bits;
    return C.structs.map(s => {
      const o = { id: s.id, role: s.role, color: s.color, rho: s.rho ?? null, visible: s.visible };
      if (s.user) { const runs = []; let st = -1; for (let q = 0; q <= b.length; q++) { const on = q < b.length && (b[q] & s.bit); if (on && st < 0) st = q; if (!on && st >= 0) { runs.push(st, q - st); st = -1; } } o.runs = runs; }
      return o;
    });
  }
  function importStructs(list) {
    if (!Array.isArray(list)) return;
    for (const o of list) {
      let s = find(o.id);
      if (!s && o.runs) s = newStruct(o.id, o.role || "oar", o.color);
      if (!s) continue;
      if (o.runs) { const b = C.sg.bits; for (let q = 0; q < b.length; q++) b[q] &= ~s.bit; for (let k = 0; k < o.runs.length; k += 2) for (let q = o.runs[k]; q < o.runs[k] + o.runs[k + 1] && q < b.length; q++) b[q] |= s.bit; }
      if (s.role !== "body" && o.role) s.role = o.role;
      s.rho = o.rho ?? null; if (o.visible !== undefined) s.visible = o.visible;
    }
    // keep the saved order (body first)
    const ord = list.map(o => o.id);
    C.structs.sort((a, b) => (a.role === "body" ? -1 : b.role === "body" ? 1 : (ord.indexOf(a.id) + 1 || 999) - (ord.indexOf(b.id) + 1 || 999)));
    applyDensity(); C.version++;
  }

  return { C, load, applyDensity, exportStructs, importStructs, radDepth, bitsAt, rhoAt, find, maskOf, names, colorOf, volume, targets,
    newStruct, removeStruct, brush, margin, boolean, interpolate, clearStruct, maskSlice, chamfer, huToRho,
    get sg() { return C.sg; }, get ph() { return C.ph; }, get structs() { return C.structs; }, get version() { return C.version; } };
})();
