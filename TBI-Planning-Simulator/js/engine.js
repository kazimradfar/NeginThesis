/* RT Planning Simulator — general plan model, approximate dose engine, two-stage optimiser and evaluation.
 * EDUCATIONAL MODEL ONLY: ray-traced pencil-free kernel = TMR(water-equivalent depth) x inverse square x fluence
 * x jaw/MLC penumbra, plus a small out-of-field tail. Radiological depth is traced through the voxel density grid
 * (so density overrides and edited structures matter). Not Monte Carlo, not commissioned for any machine. */
"use strict";
const ENG = (() => {
  const BIN = 0.5, TAIL = 3, LEAF_T = 0.006;
  const ENERGY = {
    "6 MV": { dmax: 1.5, mu: 0.047, surf: 0.42, bu: 0.45, pen: 0.28 },
    "10 MV": { dmax: 2.4, mu: 0.037, surf: 0.30, bu: 0.75, pen: 0.34 },
  };
  // cost-function scale factors (relative dose units, tuned on the thesis TBI plan)
  const K = { tpE: 43, tpU: 864, qod: 576, qud: 576, max: 2880, par: 400, eud: 3000, ser: 3000, dvh: 576, conf: 150 };
  const OBJ_TYPES = ["Target Penalty", "Target EUD", "Quadratic Underdose", "Underdose DVH", "Quadratic Overdose",
    "Overdose DVH", "Maximum Dose", "Serial", "Parallel", "Conformality"];
  const OBJ_HELP = {
    "Target Penalty": ["Prescription (Gy)", "Min. volume (%)"], "Target EUD": ["EUD (Gy)", "Cell sensitivity α (/Gy)"],
    "Quadratic Underdose": ["Dose (Gy)", "RMS (Gy)"], "Underdose DVH": ["Dose (Gy)", "Min. volume (%)"],
    "Quadratic Overdose": ["Dose (Gy)", "RMS (Gy)"], "Overdose DVH": ["Dose (Gy)", "Max. volume (%)"],
    "Maximum Dose": ["Max. dose (Gy)", "–"], "Serial": ["EUD limit (Gy)", "Power k"],
    "Parallel": ["Reference dose (Gy)", "Mean organ damage (%)"], "Conformality": ["Reference dose (Gy)", "Fall-off (cm)"],
  };
  const sig = t => 1 / (1 + Math.exp(-t));
  function tmr(E, d) {
    if (d < E.dmax) { const dd = d > 0 ? d : 0; return 1 - (1 - E.surf) * Math.exp(-dd / E.bu) - 0.02 * (E.dmax - dd) / E.dmax; }
    return Math.exp(-E.mu * (d - E.dmax));
  }
  const mod360 = a => ((a % 360) + 360) % 360;
  function arcSpan(b) { let s = b.dir === "CCW" ? mod360(b.start - b.stop) : mod360(b.stop - b.start); return s < 1e-6 ? 360 : s; }

  const state = { plan: null, cps: [], grid: null, scale: 1, history: [], fine: null, stage: 0, version: 0, gridKey: "" };

  // ---------------------------------------------------------------- control points
  function makeCP(b, bi, th, k, n, dth) {
    const E = ENERGY[b.energy] || ENERGY["6 MV"], sad = b.sad || 100, bin = Math.min(1, BIN * sad / 100);
    const nX = Math.max(1, Math.round((b.X2 - b.X1) / bin)), nY = Math.max(1, Math.round((b.Y2 - b.Y1) / bin));
    const flip = b.orient === "FFS" ? -1 : 1, cr = (b.coll || 0) * Math.PI / 180;
    const tp = (flip < 0 ? -th : th) * Math.PI / 180, s = Math.sin(tp), c = Math.cos(tp);
    const cp = { beam: bi, k, n, theta: mod360(th), dth, s, c, sad, ix: b.iso.x, iy: b.iso.y, iz: b.iso.z,
      sx: b.iso.x + sad * s, sy: b.iso.y - sad * c, flip, cc: Math.cos(cr), cs: Math.sin(cr),
      X1: b.X1, X2: b.X2, Y1: b.Y1, Y2: b.Y2, nX, nY, binX: (b.X2 - b.X1) / nX, binY: (b.Y2 - b.Y1) / nY,
      E, pen: E.pen * Math.sqrt(sad / 100), ox: nX > 1 ? nY : 0, oy: nY > 1 ? 1 : 0, segs: null };
    cp.F = new Float32Array(nX * nY).fill(1); cp.Fs = new Float32Array(nX * nY).fill(1);
    zRange(cp);
    return cp;
  }
  function zRange(cp) {
    let lo = 1e9, hi = -1e9; const T = TAIL + 1;
    for (const X of [cp.X1 - T, cp.X2 + T]) for (const Y of [cp.Y1 - T, cp.Y2 + T]) {
      const w = X * cp.cs + Y * cp.cc;
      for (const f of [(cp.sad - 45) / cp.sad, (cp.sad + 45) / cp.sad]) { const z = cp.iz + cp.flip * w * f; lo = Math.min(lo, z); hi = Math.max(hi, z); }
    }
    cp.zlo = lo; cp.zhi = hi;
  }
  function buildCPs(plan) {
    const cps = [];
    plan.beams.forEach((b, bi) => {
      if (b.off) return;
      if (b.type === "arc") {
        const span = arcSpan(b), n = Math.max(2, Math.round(span / plan.cpStep)), dth = span / n, sg = b.dir === "CCW" ? -1 : 1;
        for (let k = 0; k < n; k++) cps.push(makeCP(b, bi, b.start + sg * (k + 0.5) * dth, k, n, dth));
      } else cps.push(makeCP(b, bi, b.gantry, 0, 1, 0));
    });
    return cps;
  }

  // ---------------------------------------------------------------- kernel
  function project(cp, x, y, z, out) {
    const vx = x - cp.sx, vy = y - cp.sy, a = -vx * cp.s + vy * cp.c;
    if (a <= 1) return false;
    const mag = cp.sad / a, u = (vx * cp.c + vy * cp.s) * mag * cp.flip, w = (z - cp.iz) * mag * cp.flip;
    out[0] = u * cp.cc + w * cp.cs; out[1] = -u * cp.cs + w * cp.cc; out[3] = mag; out[4] = u; out[5] = w;
    return true;
  }
  const _p = new Float64Array(6);
  function kernel(cp, x, y, z, out) {
    if (!project(cp, x, y, z, _p)) return false;
    const X = _p[0], Y = _p[1], mag = _p[3];
    if (X < cp.X1 - TAIL || X > cp.X2 + TAIL || Y < cp.Y1 - TAIL || Y > cp.Y2 + TAIL) return false;
    const p = cp.pen;
    let e = sig((X - cp.X1) / p) * sig((cp.X2 - X) / p) * sig((Y - cp.Y1) / p) * sig((cp.Y2 - Y) / p);
    const dout = Math.max(cp.X1 - X, X - cp.X2, cp.Y1 - Y, Y - cp.Y2);
    if (dout > 0) e = Math.max(e, 0.03 * Math.exp(-dout / 3));
    const d = CASE.radDepth(x, y, z, cp.sx, cp.sy);
    if (d < 0) return false;
    out[0] = X; out[1] = Y; out[2] = tmr(cp.E, d) * mag * mag * e;
    return true;
  }
  // same as kernel() for dose-grid voxel v, with the depth cached per source position (shared by isocentres)
  const _dc = new Map();
  function kernelV(cp, grid, v, out) {
    const x = grid.x[v], y = grid.y[v], z = grid.z[v];
    if (!project(cp, x, y, z, _p)) return false;
    const X = _p[0], Y = _p[1], mag = _p[3];
    if (X < cp.X1 - TAIL || X > cp.X2 + TAIL || Y < cp.Y1 - TAIL || Y > cp.Y2 + TAIL) return false;
    const key = cp.sx.toFixed(3) + "," + cp.sy.toFixed(3);
    let c = _dc.get(key);
    if (!c) { c = new Float32Array(grid.n).fill(NaN); _dc.set(key, c); }
    let d = c[v];
    if (d !== d) { d = c[v] = CASE.radDepth(x, y, z, cp.sx, cp.sy); }
    if (d < 0) return false;
    const p = cp.pen;
    let e = sig((X - cp.X1) / p) * sig((cp.X2 - X) / p) * sig((Y - cp.Y1) / p) * sig((cp.Y2 - Y) / p);
    const dout = Math.max(cp.X1 - X, X - cp.X2, cp.Y1 - Y, Y - cp.Y2);
    if (dout > 0) e = Math.max(e, 0.03 * Math.exp(-dout / 3));
    out[0] = X; out[1] = Y; out[2] = tmr(cp.E, d) * mag * mag * e;
    return true;
  }
  // bin position: nearest bin along leaf travel (X), linear interpolation across leaf pairs (Y);
  // returns the lower bin index and the weight of the next leaf pair in _fr[1]
  const _fr = [0, 0];
  function binPos(cp, X, Y) {
    let j = Math.floor((X - cp.X1) / cp.binX); j = j < 0 ? 0 : j >= cp.nX ? cp.nX - 1 : j;
    let fy = cp.nY > 1 ? (Y - cp.Y1) / cp.binY - 0.5 : 0;
    fy = fy < 0 ? 0 : fy > cp.nY - 1.0001 ? Math.max(0, cp.nY - 1.0001) : fy;
    const i = Math.floor(fy); _fr[0] = 0; _fr[1] = fy - i;
    return j * cp.nY + i;
  }
  function sampleF(cp, F, X, Y) { const b = binPos(cp, X, Y), c = _fr[1]; return F[b] * (1 - c) + F[b + cp.oy] * c; }

  // fluence blur (leaf penumbra / transmission): 1-2-3-2-1 along leaf pairs (Y), 1-2-1 along leaf travel (X)
  function smooth(cp, src, dst) {
    const n = cp.nY, m = cp.nX;
    if (!cp._tmp || cp._tmp.length !== n * m) cp._tmp = new Float32Array(n * m);
    const t = cp._tmp;
    if (n < 5) { t.set(src); }
    else for (let j = 0; j < m; j++) {
      const r = j * n, e = r + n - 1;
      t[r] = (6 * src[r] + 2 * src[r + 1] + src[r + 2]) / 9;
      t[r + 1] = (3 * src[r] + 3 * src[r + 1] + 2 * src[r + 2] + src[r + 3]) / 9;
      for (let q = r + 2; q < e - 1; q++) t[q] = (src[q - 2] + 2 * src[q - 1] + 3 * src[q] + 2 * src[q + 1] + src[q + 2]) / 9;
      t[e - 1] = (src[e - 3] + 2 * src[e - 2] + 3 * src[e - 1] + 3 * src[e]) / 9;
      t[e] = (src[e - 2] + 2 * src[e - 1] + 6 * src[e]) / 9;
    }
    if (m < 2) { dst.set(t); return; }
    for (let j = 0; j < m; j++) {
      const r = j * n, a = (j > 0 ? j - 1 : 0) * n, c = (j < m - 1 ? j + 1 : j) * n;
      for (let i = 0; i < n; i++) dst[r + i] = 0.25 * t[a + i] + 0.5 * t[r + i] + 0.25 * t[c + i];
    }
  }

  // ---------------------------------------------------------------- dose grid
  function buildGrid(h) {
    const sg = CASE.sg, x0 = sg.x0, y0 = sg.y0, z0 = sg.z0;
    const nx = Math.ceil(sg.nx * sg.h / h), ny = Math.ceil(sg.ny * sg.h / h), nz = Math.ceil(sg.nz * sg.h / h);
    const idx = new Int32Array(nx * ny * nz).fill(-1), vx = [], vy = [], vz = [], tag = [];
    const body = CASE.structs[0].bit;
    for (let k = 0, q = 0; k < nz; k++) {
      const z = z0 + (k + 0.5) * h;
      for (let j = 0; j < ny; j++) {
        const y = y0 + (j + 0.5) * h;
        for (let i = 0; i < nx; i++, q++) {
          const x = x0 + (i + 0.5) * h, t = CASE.bitsAt(x, y, z);
          if (!(t & body)) continue;
          idx[q] = vx.length; vx.push(x); vy.push(y); vz.push(z); tag.push(t);
        }
      }
    }
    return { h, x0, y0, z0, nx, ny, nz, idx, n: vx.length, x: Float32Array.from(vx), y: Float32Array.from(vy), z: Float32Array.from(vz),
      tag: Uint32Array.from(tag), dose: new Float32Array(vx.length), eff: null, _vox: {}, key: Math.random() };
  }
  function retag(grid) {
    for (let v = 0; v < grid.n; v++) grid.tag[v] = CASE.bitsAt(grid.x[v], grid.y[v], grid.z[v]);
    grid._vox = {}; grid.eff = null; grid.dist = null;
  }
  // Monaco-style layering: a voxel belongs (for the optimiser) only to the highest structure in the list
  function computeEff(grid, plan) {
    grid._vox = {};
    if (!plan.layering) { grid.eff = grid.tag; return; }
    const S = CASE.structs, body = S[0].bit, e = new Uint32Array(grid.n);
    for (let v = 0; v < grid.n; v++) {
      const t = grid.tag[v]; let r = t & body;
      for (let s = 1; s < S.length; s++) if (t & S[s].bit) { r |= S[s].bit; break; }
      e[v] = r;
    }
    grid.eff = e;
  }
  function voxOf(grid, mask, geometric) {
    const key = (geometric ? "g" : "e") + mask;
    let a = grid._vox[key];
    if (!a) {
      const T = geometric ? grid.tag : (grid.eff || grid.tag), tmp = [];
      for (let v = 0; v < grid.n; v++) if (T[v] & mask) tmp.push(v);
      a = grid._vox[key] = Int32Array.from(tmp);
    }
    return a;
  }
  // distance (cm) from each voxel to the target (for the conformality cost function)
  function targetDist(grid, tmask) {
    if (grid.dist && grid._distMask === tmask) return grid.dist;
    const N = grid.nx * grid.ny * grid.nz, d = new Float32Array(N).fill(1e9);
    for (let q = 0; q < N; q++) { const v = grid.idx[q]; if (v >= 0 && grid.tag[v] & tmask) d[q] = 0; }
    const nx = grid.nx, nxy = nx * grid.ny;
    for (let pass = 0; pass < 2; pass++) {
      const st = pass ? -1 : 1, q0 = pass ? N - 1 : 0;
      for (let c = 0, q = q0; c < N; c++, q += st) {
        const i = q % nx, j = Math.floor(q / nx) % grid.ny, k = Math.floor(q / nxy);
        let v = d[q];
        if (st > 0) { if (i > 0) v = Math.min(v, d[q - 1] + 1); if (j > 0) v = Math.min(v, d[q - nx] + 1); if (k > 0) v = Math.min(v, d[q - nxy] + 1); }
        else { if (i < nx - 1) v = Math.min(v, d[q + 1] + 1); if (j < grid.ny - 1) v = Math.min(v, d[q + nx] + 1); if (k < grid.nz - 1) v = Math.min(v, d[q + nxy] + 1); }
        d[q] = v;
      }
    }
    const out = new Float32Array(grid.n);
    for (let q = 0; q < N; q++) { const v = grid.idx[q]; if (v >= 0) out[v] = d[q] * grid.h; }
    grid.dist = out; grid._distMask = tmask;
    return out;
  }

  // ---------------------------------------------------------------- influence, forward and backward
  function buildInfluence(cps, grid) {
    const out = [0, 0, 0];
    for (const cp of cps) {
      const vi = [], bi = [], kk = [], fx = [], fy = [];
      for (let v = 0; v < grid.n; v++) {
        const z = grid.z[v]; if (z < cp.zlo || z > cp.zhi) continue;
        if (kernelV(cp, grid, v, out) && out[2] > 1e-4) {
          vi.push(v); bi.push(binPos(cp, out[0], out[1])); fy.push(_fr[1]); kk.push(out[2]);
        }
      }
      cp.vi = Int32Array.from(vi); cp.bi = Int32Array.from(bi); cp.kk = Float32Array.from(kk); cp.fy = Float32Array.from(fy);
    }
    _dc.clear();
  }
  function forwardCP(cp, D, mult) {
    const vi = cp.vi, bi = cp.bi, kk = cp.kk, fy = cp.fy, F = cp.Fs, oy = cp.oy;
    for (let q = 0; q < vi.length; q++) { const b = bi[q], c = fy[q]; D[vi[q]] += (F[b] + (F[b + oy] - F[b]) * c) * kk[q] * mult; }
  }
  function forward(cps, D, smoothFirst = true) {
    D.fill(0);
    for (const cp of cps) { if (smoothFirst) smooth(cp, cp.F, cp.Fs); forwardCP(cp, D, state.scale); }
  }
  function backwardCP(cp, g, G) {
    G.fill(0);
    const vi = cp.vi, bi = cp.bi, kk = cp.kk, fy = cp.fy, oy = cp.oy, sc = state.scale;
    for (let q = 0; q < vi.length; q++) { const b = bi[q], c = fy[q], gk = g[vi[q]] * kk[q] * sc; G[b] += gk * (1 - c); G[b + oy] += gk * c; }
    if (!cp._g2 || cp._g2.length !== G.length) cp._g2 = new Float32Array(G.length);
    smooth(cp, G, cp._g2); G.set(cp._g2);
  }

  // ---------------------------------------------------------------- apertures (conformal MLC, blocks, wedges)
  function apertureFor(cp, grid, mask, marginCm) {
    const rowsL = new Float32Array(cp.nY).fill(1e9), rowsR = new Float32Array(cp.nY).fill(-1e9), o = _p;
    const vox = voxOf(grid, mask, true), hh = grid.h / 2;
    for (let q = 0; q < vox.length; q++) {
      const v = vox[q];
      if (grid.z[v] < cp.zlo || grid.z[v] > cp.zhi || !project(cp, grid.x[v], grid.y[v], grid.z[v], o)) continue;
      const X = o[0], Y = o[1], r0 = Math.floor((Y - hh - cp.Y1) / cp.binY), r1 = Math.floor((Y + hh - cp.Y1) / cp.binY);
      for (let r = Math.max(0, r0); r <= Math.min(cp.nY - 1, r1); r++) { if (X - hh < rowsL[r]) rowsL[r] = X - hh; if (X + hh > rowsR[r]) rowsR[r] = X + hh; }
    }
    // margin across leaves (dilate rows) and along leaf travel
    const R = Math.max(0, Math.round(marginCm / cp.binY)), L = new Float32Array(cp.nY), Rr = new Float32Array(cp.nY);
    for (let r = 0; r < cp.nY; r++) {
      let a = 1e9, b = -1e9;
      for (let t = Math.max(0, r - R); t <= Math.min(cp.nY - 1, r + R); t++) { a = Math.min(a, rowsL[t]); b = Math.max(b, rowsR[t]); }
      if (b < a) { L[r] = Rr[r] = 0.5 * (cp.X1 + cp.X2); continue; }
      L[r] = Math.max(cp.X1, a - marginCm); Rr[r] = Math.min(cp.X2, b + marginCm);
      if (Rr[r] < L[r]) L[r] = Rr[r] = 0.5 * (cp.X1 + cp.X2);
    }
    return { l: L, r: Rr };
  }
  function apertureFluence(cp, ap, out, w = 1) {
    for (let j = 0; j < cp.nX; j++) {
      const x0 = cp.X1 + j * cp.binX, x1 = x0 + cp.binX;
      for (let i = 0; i < cp.nY; i++) {
        const cov = Math.max(0, Math.min(1, (Math.min(ap.r[i], x1) - Math.max(ap.l[i], x0)) / cp.binX));
        out[j * cp.nY + i] += w * (cov + LEAF_T * (1 - cov));
      }
    }
  }
  function wedgeFactor(cp, b, j, i) {
    if (!b.wedge || !b.wedge.angle) return 1;
    const X = cp.X1 + (j + 0.5) * cp.binX, Y = cp.Y1 + (i + 0.5) * cp.binY;
    const s = { "+X": X, "-X": -X, "+Y": Y, "-Y": -Y }[b.wedge.dir || "+X"];
    return Math.exp(-cp.E.mu * Math.tan(b.wedge.angle * Math.PI / 180) * s * 2.2);
  }
  function blockFluence(cp, grid, b, out) {
    const m = CASE.maskOf(b.blockStruct || "Lungs");
    const hit = new Uint8Array(cp.nX * cp.nY), vox = voxOf(grid, m, true), o = _p;
    for (let q = 0; q < vox.length; q++) {
      const v = vox[q]; if (!project(cp, grid.x[v], grid.y[v], grid.z[v], o)) continue;
      const j = Math.floor((o[0] - cp.X1) / cp.binX), i = Math.floor((o[1] - cp.Y1) / cp.binY);
      if (j >= 0 && i >= 0 && j < cp.nX && i < cp.nY) hit[j * cp.nY + i] = 1;
    }
    // close small holes (one dilation), then contract the block by its margin so it sits inside the projected lung
    let cur = new Uint8Array(hit.length);
    for (let j = 0; j < cp.nX; j++) for (let i = 0; i < cp.nY; i++) {
      const q = j * cp.nY + i;
      cur[q] = hit[q] || (i > 0 && hit[q - 1]) || (i < cp.nY - 1 && hit[q + 1]) || (j > 0 && hit[q - cp.nY]) || (j < cp.nX - 1 && hit[q + cp.nY]) ? 1 : 0;
    }
    let er = 1 + Math.round((b.blockMargin ?? 1) / Math.min(cp.binX, cp.binY));
    while (er-- > 0) {
      const nx = new Uint8Array(cur.length);
      for (let j = 0; j < cp.nX; j++) for (let i = 0; i < cp.nY; i++) {
        const q = j * cp.nY + i;
        nx[q] = cur[q] && j > 0 && j < cp.nX - 1 && i > 0 && i < cp.nY - 1 && cur[q - 1] && cur[q + 1] && cur[q - cp.nY] && cur[q + cp.nY] ? 1 : 0;
      }
      cur = nx;
    }
    const T = b.blockT ?? 0.5;
    for (let q = 0; q < out.length; q++) out[q] = cur[q] ? T : 1;
    cp.block = cur;
  }
  // initial / forward-planned fluence of every control point
  function initFluence(plan, grid) {
    const tmask = CASE.maskOf(plan.target);
    // every beam starts with the same share of dose: an arc's fluence is spread over its control points
    const nRef = Math.max(1, ...state.cps.map(c => c.n));
    for (const cp of state.cps) {
      cp.Fscale = nRef / cp.n;
      const b = plan.beams[cp.beam], F = cp.F; F.fill(0); cp.segs = null; cp.block = null;
      const mode = b.mlc || "optimised";
      if (mode === "open") { F.fill(1); cp.segs = [{ l: new Float32Array(cp.nY).fill(cp.X1), r: new Float32Array(cp.nY).fill(cp.X2), w: 1 }]; }
      else if (mode === "blocks") blockFluence(cp, grid, b, F);
      else {
        const ap = apertureFor(cp, grid, b.mlcTarget ? CASE.maskOf(b.mlcTarget) : tmask, mode === "conformal" ? (b.margin ?? 0.7) : 1.0);
        if (mode === "conformal") { apertureFluence(cp, ap, F); cp.segs = [{ l: ap.l, r: ap.r, w: 1 }]; }
        else { apertureFluence(cp, ap, F); for (let q = 0; q < F.length; q++) F[q] = 0.08 + 0.92 * F[q]; }
      }
      const w = (b.weight ?? 1) * (mode === "optimised" ? cp.Fscale : 1);
      for (let j = 0; j < cp.nX; j++) for (let i = 0; i < cp.nY; i++) F[j * cp.nY + i] *= w * wedgeFactor(cp, b, j, i);
      if (cp.segs) cp.segs.forEach(s => s.w = w);
      cp.base = Float32Array.from(F);
    }
  }

  // ---------------------------------------------------------------- objectives
  function evalObjectives(plan, grid, D, g, iter) {
    g.fill(0);
    let total = 0;
    const rx = plan.rx, tmask = CASE.maskOf(plan.target);
    for (const ob of plan.objectives) {
      ob._f = 0; if (!ob.on) continue;
      const mask = CASE.maskOf(ob.struct); if (!mask) continue;
      const vox = voxOf(grid, mask), n = vox.length; if (!n) continue;
      if (ob.mode === "constraint" && ob._mult === undefined) ob._mult = 5;
      const w = ob.weight * (ob.mode === "constraint" ? ob._mult : 1), D0 = ob.dose;
      let f = 0;
      switch (ob.type) {
        case "Target Penalty": {
          const lo = D0 * 0.95; let hit = 0;
          for (let q = 0; q < n; q++) {
            const v = vox[q], d = D[v], e = (d - D0) / rx, u = Math.min(0, (d - lo) / rx);
            f += K.tpE * e * e + K.tpU * u * u; g[v] += w * (2 * K.tpE * e + 2 * K.tpU * u) / (rx * n); if (d >= D0) hit++;
          }
          f /= n; ob._ach = `V≥${D0} Gy ${(100 * hit / n).toFixed(1)}%`; break;
        }
        case "Quadratic Overdose": case "Quadratic Underdose": {
          const over = ob.type === "Quadratic Overdose"; let s2 = 0;
          for (let q = 0; q < n; q++) { const d = D[vox[q]], e = over ? Math.max(0, d - D0) : Math.max(0, D0 - d); s2 += e * e; }
          // penalty = mean squared excess; the RMS parameter is shown against the achieved RMS
          const rms = Math.sqrt(s2 / n); f = K.qod * s2 / (n * rx * rx); ob._ach = `RMS ${rms.toFixed(2)} Gy (≤ ${ob.extra || 0})`;
          for (let q = 0; q < n; q++) {
            const v = vox[q], d = D[v], e = over ? Math.max(0, d - D0) : -Math.max(0, D0 - d);
            if (e) g[v] += w * 2 * K.qod * e / (rx * rx * n);
          }
          break;
        }
        case "Maximum Dose": {
          let mx = 0;
          for (let q = 0; q < n; q++) { const v = vox[q], d = D[v], e = Math.max(0, d - D0) / rx; f += K.max * e * e; g[v] += w * 2 * K.max * e / (rx * n); if (d > mx) mx = d; }
          f /= n; ob._ach = `max ${mx.toFixed(2)} Gy`; break;
        }
        case "Parallel": {
          const p = 4, target = ob.extra / 100;
          if (!grid._dd || grid._dd.length !== grid.n) grid._dd = new Float32Array(grid.n);
          const dd = grid._dd; let mod = 0;
          for (let q = 0; q < n; q++) {
            const v = vox[q], d = Math.max(D[v], 1e-3), r2 = (d / D0) * (d / D0), r = r2 * r2;
            mod += r / (1 + r); dd[v] = p * r / ((1 + r) * (1 + r) * d);
          }
          mod /= n; const ex = Math.max(0, mod - target); f = K.par * ex * ex;
          if (ex > 0) for (let q = 0; q < n; q++) { const v = vox[q]; g[v] += w * 2 * K.par * ex * dd[v] / n; }
          ob._ach = `damage ${(100 * mod).toFixed(1)}%`; break;
        }
        case "Serial": {
          const k = Math.max(1, ob.extra || 12); let M = 0;
          for (let q = 0; q < n; q++) M += Math.pow(Math.max(0, D[vox[q]]) / D0, k);
          M /= n; const ge = Math.pow(M, 1 / k), ex = Math.max(0, ge - 1); f = K.ser * ex * ex;
          if (ex > 0) { const c = Math.pow(M, 1 / k - 1); for (let q = 0; q < n; q++) { const v = vox[q]; g[v] += w * 2 * K.ser * ex * c * Math.pow(Math.max(0, D[v]) / D0, k - 1) / (n * D0); } }
          ob._ach = `EUD ${(ge * D0).toFixed(2)} Gy`; break;
        }
        case "Target EUD": {
          const al = Math.max(0.01, ob.extra || 0.5); let mn = 1e9;
          for (let q = 0; q < n; q++) mn = Math.min(mn, D[vox[q]]);
          let S = 0; for (let q = 0; q < n; q++) S += Math.exp(-al * (D[vox[q]] - mn));
          S /= n; const eud = mn - Math.log(S) / al, ex = Math.max(0, D0 - eud) / rx; f = K.eud * ex * ex;
          if (ex > 0) for (let q = 0; q < n; q++) { const v = vox[q]; g[v] -= w * 2 * K.eud * ex * Math.exp(-al * (D[v] - mn)) / (n * S * rx); }
          ob._ach = `EUD ${eud.toFixed(2)} Gy`; break;
        }
        case "Overdose DVH": case "Underdose DVH": {
          const over = ob.type === "Overdose DVH", vals = new Float32Array(n);
          for (let q = 0; q < n; q++) vals[q] = D[vox[q]];
          const sorted = Float32Array.from(vals).sort(), frac = Math.max(0, Math.min(100, ob.extra)) / 100;
          const Dv = sorted[Math.max(0, Math.min(n - 1, Math.floor((1 - frac) * n)))];
          let cnt = 0; for (let q = 0; q < n; q++) if (over ? vals[q] > D0 : vals[q] >= D0) cnt++;
          ob._ach = `V${D0} Gy = ${(100 * cnt / n).toFixed(1)}%`;
          if (over ? Dv > D0 : Dv < D0) for (let q = 0; q < n; q++) {
            const v = vox[q], d = vals[q];
            if (over && d > D0 && d <= Dv) { const e = (d - D0) / rx; f += K.dvh * e * e; g[v] += w * 2 * K.dvh * e / (rx * n); }
            if (!over && d < D0 && d >= Dv) { const e = (D0 - d) / rx; f += K.dvh * e * e; g[v] -= w * 2 * K.dvh * e / (rx * n); }
          }
          f /= n; break;
        }
        case "Conformality": {
          // allowed dose falls off exponentially from the target surface (first 0.5 cm free) down to 25 % of the reference
          const dist = targetDist(grid, tmask), lam = Math.max(0.2, ob.extra || 2.5); let bad = 0, cnt = 0;
          for (let q = 0; q < n; q++) {
            const v = vox[q]; if (grid.tag[v] & tmask) continue; cnt++;
            const allow = D0 * Math.max(0.25, 1.05 * Math.exp(-Math.max(0, 0.8 * dist[v] - 0.5) / lam)), e = Math.max(0, D[v] - allow) / rx;
            if (e > 0) { bad++; f += K.conf * e * e; g[v] += w * 2 * K.conf * e / (rx * n); }
          }
          f /= n; ob._ach = `above fall-off ${(100 * bad / Math.max(1, cnt)).toFixed(1)}%`; break;
        }
      }
      if (ob.mode === "constraint" && iter > 0 && iter % 15 === 0 && f > 1e-4) ob._mult = Math.min(500, ob._mult * 1.5);
      ob._f = ob.weight * f; total += ob._f;
    }
    return total;
  }

  // ---------------------------------------------------------------- normalisation
  function meanIn(grid, D, mask) { const v = voxOf(grid, mask, true); let s = 0; for (let q = 0; q < v.length; q++) s += D[v[q]]; return v.length ? s / v.length : 0; }
  function pctIn(grid, D, mask, p) {
    const v = voxOf(grid, mask, true); if (!v.length) return 0;
    const a = new Float32Array(v.length); for (let q = 0; q < v.length; q++) a[q] = D[v[q]]; a.sort();
    return a[Math.max(0, Math.min(a.length - 1, Math.floor((1 - p / 100) * a.length)))];
  }
  // factor that brings the dose to the prescription with the chosen rule; Dfix = dose that is not scaled
  function normFactor(plan, grid, Dact, Dfix) {
    const m = CASE.maskOf(plan.target), rx = plan.rx, rule = plan.norm || "mean";
    if (rule === "none" || !m) return 1;
    if (rule === "mean" || !Dfix) {
      const ma = meanIn(grid, Dact, m), mf = Dfix ? meanIn(grid, Dfix, m) : 0;
      if (rule === "mean") return ma > 0 ? Math.max(0, rx - mf) / ma : 1;
    }
    // percentile rules: iterate the factor (Dfix + s Dact)
    const p = rule === "D95" ? 95 : rule === "D98" ? 98 : 50;
    let s = 1;
    const tmp = new Float32Array(grid.n);
    for (let it = 0; it < 6; it++) {
      for (let v = 0; v < grid.n; v++) tmp[v] = (Dfix ? Dfix[v] : 0) + s * Dact[v];
      const dp = pctIn(grid, tmp, m, p); if (dp <= 0) break;
      s *= rx / dp; if (Math.abs(dp - rx) < 1e-3 * rx) break;
    }
    return s;
  }

  // ---------------------------------------------------------------- setup
  function setup(plan) {
    state.plan = plan;
    const h = plan.params.grid || CASE.ph.grid || 1;
    const key = CASE.version + "_" + h + "_" + CASE.C.densVersion;
    if (!state.grid || state.gridKey !== key) {
      if (state.grid && state.grid.h === h && state.gridKey.split("_")[2] === String(CASE.C.densVersion) && state._caseLoad === CASE.C.ph.id) retag(state.grid);
      else state.grid = buildGrid(h);
      state.gridKey = key; state._caseLoad = CASE.C.ph.id;
    }
    computeEff(state.grid, plan);
    state.cps = buildCPs(plan);
    buildInfluence(state.cps, state.grid);
    initFluence(plan, state.grid);
    state.scale = 1; forward(state.cps, state.grid.dose);
    const m = CASE.maskOf(plan.target), mp = m ? meanIn(state.grid, state.grid.dose, m) : 0;
    state.scale = mp > 0 ? plan.rx / mp : 1;
    for (let v = 0; v < state.grid.n; v++) state.grid.dose[v] *= state.scale;
    normaliseAll();
    state.stage = 0; state.history = []; state.fine = null; state.version++;
    plan.objectives.forEach(o => { delete o._mult; });
  }
  function normaliseAll() {
    const plan = state.plan, grid = state.grid;
    const s = normFactor(plan, grid, grid.dose, null);
    if (s !== 1 && isFinite(s) && s > 0) {
      for (const cp of state.cps) { for (let q = 0; q < cp.F.length; q++) cp.F[q] *= s; if (cp.segs) cp.segs.forEach(g => g.w *= s); }
      for (let v = 0; v < grid.n; v++) grid.dose[v] *= s;
    }
  }
  // forward planning (3D-CRT, conventional TBI): recompute from the beam settings
  function calculate() { const keep = state.plan; setup(keep); state.stage = 3; }

  // ---------------------------------------------------------------- Stage 1: fluence optimisation
  const SMOOTH_W = { Off: 0, Low: 0.0003, Medium: 0.0008, High: 0.003 };
  function activeSplit(part) {
    const plan = state.plan, act = [], fix = [];
    for (const cp of state.cps) {
      const b = plan.beams[cp.beam], opt = (b.mlc || "optimised") === "optimised", inPart = !part || (b.part || 1) === part;
      (opt && inPart ? act : fix).push(cp);
    }
    return { act, fix };
  }
  function optimise(nIter, opt, onStep, onDone) {
    const plan = state.plan, grid = state.grid, { act, fix } = activeSplit(opt.part);
    if (!act.length) { onDone && onDone("No beams with optimised MLC in this selection"); return; }
    for (const cp of act) cp.segs = null;
    const Dfix = new Float32Array(grid.n), Dact = new Float32Array(grid.n), D = grid.dose, g = new Float32Array(grid.n);
    forward(fix, Dfix);
    const grads = act.map(cp => new Float32Array(cp.F.length)), m1 = act.map(cp => new Float32Array(cp.F.length)), m2 = act.map(cp => new Float32Array(cp.F.length));
    const lr = 0.06, b1 = 0.9, b2 = 0.999, sw = SMOOTH_W[plan.params.smoothing] ?? 0.0008, tmask = CASE.maskOf(plan.target);
    let it = 0; state.history = [];
    const renorm = () => {
      const mf = meanIn(grid, Dfix, tmask), ma = meanIn(grid, Dact, tmask);
      if (ma > 0) { const s = Math.max(0.05, (plan.rx - mf) / ma); for (const cp of act) { const F = cp.F; for (let q = 0; q < F.length; q++) F[q] *= s; } for (let v = 0; v < grid.n; v++) Dact[v] *= s; }
    };
    function step() {
      const t0 = performance.now();
      while (it < nIter && performance.now() - t0 < 40) {
        forward(act, Dact); renorm();
        for (let v = 0; v < grid.n; v++) D[v] = Dfix[v] + Dact[v];
        const obj = evalObjectives(plan, grid, D, g, it);
        for (let c = 0; c < act.length; c++) backwardCP(act[c], g, grads[c]);
        it++;
        const c1 = 1 / (1 - Math.pow(b1, it)), c2 = 1 / (1 - Math.pow(b2, it)), lrt = lr * (0.25 + 0.75 * Math.max(0, 1 - it / nIter));
        for (let c = 0; c < act.length; c++) {
          const cp = act[c], F = cp.F, G = grads[c], M = m1[c], V = m2[c], nY = cp.nY, nX = cp.nX, fs = cp.Fscale || 1, lc = lrt * fs, fmax = 8 * fs;
          for (let j = 0, q = 0; j < nX; j++) for (let i = 0; i < nY; i++, q++) {
            const lap = (j > 0 ? F[q] - F[q - nY] : 0) + (j < nX - 1 ? F[q] - F[q + nY] : 0);
            const gr = G[q] + sw * lap / fs;
            M[q] = b1 * M[q] + (1 - b1) * gr; V[q] = b2 * V[q] + (1 - b2) * gr * gr;
            const f = F[q] - lc * (M[q] * c1) / (Math.sqrt(V[q] * c2) + 1e-8);
            F[q] = f < 0 ? 0 : f > fmax ? fmax : f;
          }
        }
        state.history.push(obj);
      }
      if (onStep) onStep(it, nIter, state.history[state.history.length - 1]);
      if (it < nIter) { requestAnimationFrame(step); return; }
      forward(act, Dact);
      const s = normFactor(plan, grid, Dact, Dfix);
      for (const cp of act) { for (let q = 0; q < cp.F.length; q++) cp.F[q] *= s; smooth(cp, cp.F, cp.Fs); }
      for (let v = 0; v < grid.n; v++) D[v] = Dfix[v] + s * Dact[v];
      evalObjectives(plan, grid, D, g, -1);
      state.stage = 1; state.fine = null; state.version++;
      onDone && onDone();
    }
    requestAnimationFrame(step);
  }

  // 3D-CRT: optimise beam weights only (forward-planned apertures and wedges are kept)
  function optimiseWeights(nIter, onStep, onDone) {
    const plan = state.plan, grid = state.grid, D = grid.dose, g = new Float32Array(grid.n);
    const beams = [...new Set(state.cps.map(c => c.beam))], per = beams.map(b => state.cps.filter(c => c.beam === b));
    const Db = per.map(cps => { const d = new Float32Array(grid.n); const keep = cps.map(c => c.F.slice()); cps.forEach(c => c.F.set(c.base)); forward(cps, d); cps.forEach((c, i) => c.F.set(keep[i])); return d; });
    const w = beams.map(b => plan.beams[b].weight ?? 1), M = w.map(() => 0), V = w.map(() => 0);
    let it = 0; state.history = [];
    const tmask = CASE.maskOf(plan.target);
    function step() {
      const t0 = performance.now();
      while (it < nIter && performance.now() - t0 < 40) {
        D.fill(0); for (let b = 0; b < w.length; b++) for (let v = 0; v < grid.n; v++) D[v] += w[b] * Db[b][v];
        const mp = meanIn(grid, D, tmask); if (mp > 0) { const s = plan.rx / mp; for (let b = 0; b < w.length; b++) w[b] *= s; for (let v = 0; v < grid.n; v++) D[v] *= s; }
        const obj = evalObjectives(plan, grid, D, g, it); it++;
        for (let b = 0; b < w.length; b++) {
          let gr = 0; const d = Db[b]; for (let v = 0; v < grid.n; v++) gr += g[v] * d[v];
          M[b] = 0.9 * M[b] + 0.1 * gr; V[b] = 0.999 * V[b] + 0.001 * gr * gr;
          w[b] = Math.max(0, w[b] - 0.03 * (M[b] / (1 - Math.pow(0.9, it))) / (Math.sqrt(V[b] / (1 - Math.pow(0.999, it))) + 1e-9));
        }
        state.history.push(obj);
      }
      onStep && onStep(it, nIter, state.history[state.history.length - 1]);
      if (it < nIter) { requestAnimationFrame(step); return; }
      const sum = w.reduce((a, b) => a + b, 0) || 1;
      beams.forEach((b, i) => plan.beams[b].weight = +(w[i] * beams.length / sum).toFixed(3));
      calculate(); onDone && onDone();
    }
    requestAnimationFrame(step);
  }

  // ---------------------------------------------------------------- Stage 2: segmentation and segment weights
  // VMAT: the fluence of each control point is split into a few apertures (sub-control points swept while the
  // gantry moves through the control-point interval); leaf travel between consecutive apertures is reported.
  function sequenceArc(cps, P) {
    let prev = null, worst = 0;
    for (const cp of cps) {
      sequenceStatic(cp, { ...P, levels: P.vmatLevels || 5, maxSegs: P.vmatSegs || 6, minArea: P.vmatMinArea ?? 1 });
      if (!cp.segs.length) { const l = new Float32Array(cp.nY).fill(0.5 * (cp.X1 + cp.X2)); cp.segs = [{ l, r: Float32Array.from(l), w: 0 }]; }
      // order the apertures to reduce leaf travel (nearest first) and measure the largest leaf move per degree
      const left = cp.segs.slice(), ord = [];
      let cur = prev;
      while (left.length) {
        let bi = 0, bd = 1e9;
        left.forEach((sg, i) => { if (!cur) return; let d = 0; for (let r = 0; r < cp.nY; r++) d = Math.max(d, Math.abs(sg.l[r] - cur.l[r]), Math.abs(sg.r[r] - cur.r[r])); if (d < bd) { bd = d; bi = i; } });
        const sg = left.splice(bi, 1)[0]; if (cur && cp.dth) worst = Math.max(worst, bd / (cp.dth / cp.segs.length)); ord.push(sg); cur = sg;
      }
      cp.segs = ord; prev = cur;
    }
    return worst;
  }
  function sequenceStatic(cp, P) {
    // intensity-level decomposition (one segment per level and run), then drop small segments
    let mx = 0; for (const f of cp.F) mx = Math.max(mx, f);
    const L = Math.max(2, P.levels || 7), step = mx / L, q = new Int16Array(cp.F.length);
    for (let t = 0; t < q.length; t++) q[t] = Math.round(cp.F[t] / (step || 1));
    const segs = [];
    for (let lev = 1; lev <= L; lev++) {
      const runs = [];
      for (let i = 0; i < cp.nY; i++) {
        const rr = []; let a = -1;
        for (let j = 0; j <= cp.nX; j++) { const on = j < cp.nX && q[j * cp.nY + i] >= lev; if (on && a < 0) a = j; if (!on && a >= 0) { rr.push([a, j]); a = -1; } }
        runs.push(rr);
      }
      const nseg = Math.max(0, ...runs.map(r => r.length));
      for (let s = 0; s < nseg; s++) {
        const l = new Float32Array(cp.nY), r = new Float32Array(cp.nY); let area = 0;
        for (let i = 0; i < cp.nY; i++) {
          const run = runs[i][s];
          if (run) { l[i] = cp.X1 + run[0] * cp.binX; r[i] = cp.X1 + run[1] * cp.binX; area += (r[i] - l[i]) * cp.binY; }
          else l[i] = r[i] = 0.5 * (cp.X1 + cp.X2);
        }
        if (area >= (P.minArea ?? 4)) segs.push({ l, r, w: step, area });
      }
    }
    segs.sort((a, b) => b.w * b.area - a.w * a.area);
    cp.segs = segs.slice(0, P.maxSegs || 10);
  }
  function deliverable(cp) {
    cp.F.fill(0);
    for (const s of cp.segs) { if (!s.A) { s.A = new Float32Array(cp.F.length); apertureFluence(cp, s, s.A, 1); } for (let q = 0; q < cp.F.length; q++) cp.F[q] += s.w * s.A[q]; }
  }
  function stage2(nIter, opt, onStep, onDone) {
    const plan = state.plan, grid = state.grid, P = plan.params, { act, fix } = activeSplit(opt.part);
    if (!act.length) { onDone && onDone("No beams with optimised MLC in this selection"); return; }
    if (state.stage < 1) { onDone && onDone("Run Stage 1 first"); return; }
    // sequencing
    const byBeam = {};
    for (const cp of act) (byBeam[cp.beam] = byBeam[cp.beam] || []).push(cp);
    state.leafPerDeg = 0;
    for (const b in byBeam) { if (plan.beams[b].type === "arc") state.leafPerDeg = Math.max(state.leafPerDeg, sequenceArc(byBeam[b], P)); else byBeam[b].forEach(cp => sequenceStatic(cp, P)); }
    for (const cp of act) deliverable(cp);
    const Dfix = new Float32Array(grid.n), Dact = new Float32Array(grid.n), D = grid.dose, g = new Float32Array(grid.n);
    forward(fix, Dfix);
    const segs = []; for (const cp of act) for (const s of cp.segs) segs.push([cp, s]);
    const M = new Float32Array(segs.length), V = new Float32Array(segs.length), G = act.map(cp => new Float32Array(cp.F.length));
    const tmask = CASE.maskOf(plan.target); let it = 0; state.history = [];
    const muOf = (cp, w) => w * state.scale * 100 / plan.fx * (cp.sad / 100) ** 2;
    function step() {
      const t0 = performance.now();
      while (it < nIter && performance.now() - t0 < 40) {
        for (const cp of act) deliverable(cp);
        forward(act, Dact);
        const mf = meanIn(grid, Dfix, tmask), ma = meanIn(grid, Dact, tmask);
        if (ma > 0) { const s = Math.max(0.05, (plan.rx - mf) / ma); for (const [, sg] of segs) sg.w *= s; for (let v = 0; v < grid.n; v++) Dact[v] *= s; }
        for (let v = 0; v < grid.n; v++) D[v] = Dfix[v] + Dact[v];
        const obj = evalObjectives(plan, grid, D, g, it);
        act.forEach((cp, c) => backwardCP(cp, g, G[c]));
        it++;
        segs.forEach(([cp, sg], k) => {
          const Gc = G[act.indexOf(cp)]; let gr = 0; for (let q = 0; q < sg.A.length; q++) gr += Gc[q] * sg.A[q];
          M[k] = 0.9 * M[k] + 0.1 * gr; V[k] = 0.999 * V[k] + 0.001 * gr * gr;
          sg.w = Math.max(0, sg.w - 0.03 * sg.w0g(it) * (M[k] / (1 - Math.pow(0.9, it))) / (Math.sqrt(V[k] / (1 - Math.pow(0.999, it))) + 1e-12));
        });
        state.history.push(obj);
      }
      onStep && onStep(it, nIter, state.history[state.history.length - 1]);
      if (it < nIter) { requestAnimationFrame(step); return; }
      // minimum MU per segment, then final normalisation
      for (const cp of act) { const lim = plan.beams[cp.beam].type === "arc" ? 0.05 : (P.minMU ?? 2); const keep = cp.segs.filter(s => muOf(cp, s.w) >= lim); if (keep.length) cp.segs = keep; deliverable(cp); }
      forward(act, Dact);
      const s = normFactor(plan, grid, Dact, Dfix);
      for (const cp of act) { cp.segs.forEach(sg => sg.w *= s); deliverable(cp); smooth(cp, cp.F, cp.Fs); }
      for (let v = 0; v < grid.n; v++) D[v] = Dfix[v] + s * Dact[v];
      evalObjectives(plan, grid, D, g, -1);
      state.stage = 2; state.fine = null; state.version++;
      onDone && onDone();
    }
    // step size relative to each segment's starting weight
    for (const [, sg] of segs) { const w0 = Math.max(sg.w, 1e-3); sg.w0g = () => w0; }
    requestAnimationFrame(step);
  }

  // ---------------------------------------------------------------- point dose and fine calculation
  const _o = [0, 0, 0];
  function doseFrom(cps, x, y, z) {
    let d = 0;
    for (const cp of cps) { if (z < cp.zlo || z > cp.zhi) continue; if (kernel(cp, x, y, z, _o)) d += sampleF(cp, cp.Fs, _o[0], _o[1]) * _o[2]; }
    return d * state.scale;
  }
  function doseAt(x, y, z) { if (!(CASE.bitsAt(x, y, z) & 1)) return 0; return doseFrom(state.cps, x, y, z); }
  function computeOn(grid, cps, onStep, onDone) {
    const dose = new Float32Array(grid.n); let v = 0;
    function step() {
      const t0 = performance.now();
      while (v < grid.n && performance.now() - t0 < 40) { dose[v] = doseFrom(cps, grid.x[v], grid.y[v], grid.z[v]); v++; }
      onStep && onStep(v, grid.n);
      if (v < grid.n) requestAnimationFrame(step); else onDone(dose);
    }
    requestAnimationFrame(step);
  }
  function finalCalc(onStep, onDone) {
    const h = Math.max(0.25, (state.grid.h) / 2), grid = buildGrid(h);
    computeEff(grid, state.plan);
    computeOn(grid, state.cps, onStep, dose => { grid.dose = dose; state.fine = grid; onDone && onDone(); });
  }
  // trilinear sample of any dose array defined on a grid
  function sampleGrid(grid, dose, x, y, z) {
    const fx = (x - grid.x0) / grid.h - 0.5, fy = (y - grid.y0) / grid.h - 0.5, fz = (z - grid.z0) / grid.h - 0.5;
    const i = Math.floor(fx), j = Math.floor(fy), k = Math.floor(fz), a = fx - i, b = fy - j, c = fz - k;
    let s = 0;
    for (let dk = 0; dk < 2; dk++) for (let dj = 0; dj < 2; dj++) for (let di = 0; di < 2; di++) {
      const I = i + di, J = j + dj, Kk = k + dk;
      if (I < 0 || J < 0 || Kk < 0 || I >= grid.nx || J >= grid.ny || Kk >= grid.nz) continue;
      const v = grid.idx[(Kk * grid.ny + J) * grid.nx + I]; if (v < 0) continue;
      s += dose[v] * (di ? a : 1 - a) * (dj ? b : 1 - b) * (dk ? c : 1 - c);
    }
    return s;
  }

  // ---------------------------------------------------------------- robustness (isocentre / set-up shifts)
  function robust(shift, beamFilter, onStep, onDone) {
    const shifted = state.cps.filter(cp => !beamFilter || beamFilter(cp.beam)).map(cp => {
      const c = Object.assign({}, cp);
      c.ix = cp.ix + shift.x; c.iy = cp.iy + shift.y; c.iz = cp.iz + shift.z;
      c.sx = c.ix + cp.sad * cp.s; c.sy = c.iy - cp.sad * cp.c; zRange(c); return c;
    });
    const others = beamFilter ? state.cps.filter(cp => !beamFilter(cp.beam)) : [];
    computeOn(state.grid, [...shifted, ...others], onStep, onDone);
  }

  // ---------------------------------------------------------------- evaluation
  function dvh(grid, dose, mask, dmax, nb = 300) {
    const vox = voxOf(grid, mask, true), vals = new Float32Array(vox.length);
    for (let q = 0; q < vox.length; q++) vals[q] = dose[vox[q]];
    vals.sort();
    const n = vals.length, curve = [];
    for (let i = 0; i <= nb; i++) {
      const d = dmax * i / nb; let lo = 0, hi = n;
      while (lo < hi) { const mid = (lo + hi) >> 1; if (vals[mid] < d) lo = mid + 1; else hi = mid; }
      curve.push([d, n ? 100 * (n - lo) / n : 0]);
    }
    let sum = 0; for (let q = 0; q < n; q++) sum += vals[q];
    const Dp = p => n ? vals[Math.min(n - 1, Math.max(0, Math.floor((1 - p / 100) * n)))] : 0;
    const Vd = d => { let lo = 0, hi = n; while (lo < hi) { const mid = (lo + hi) >> 1; if (vals[mid] < d) lo = mid + 1; else hi = mid; } return n ? 100 * (n - lo) / n : 0; };
    return { curve, mean: n ? sum / n : 0, min: n ? vals[0] : 0, max: n ? vals[n - 1] : 0, Dp, Vd, n, cc: n * grid.h ** 3 };
  }
  function muInfo() {
    const plan = state.plan, perBeam = {}; let total = 0, time = 0;
    const P = plan.params, dr = P.maxDoseRate || 600;
    plan.beams.forEach((b, i) => { if (!b.off) perBeam[i] = { mu: 0, segs: 0, time: 0 }; });
    for (const cp of state.cps) {
      const b = plan.beams[cp.beam], f = state.scale * 100 / plan.fx * (cp.sad / 100) ** 2;
      let mu;
      if (cp.segs) { mu = 0; for (const s of cp.segs) mu += s.w * f; perBeam[cp.beam].segs += cp.segs.length; }
      else { let mx = 0; for (const v of cp.Fs) mx = Math.max(mx, v); mu = mx * f * (b.type === "arc" ? 1 : 1.6); perBeam[cp.beam].segs += 1; }
      perBeam[cp.beam].mu += mu; total += mu;
      if (b.type === "arc") perBeam[cp.beam].time += Math.max(cp.dth / (P.gantrySpeed || 6), mu / (dr / 60));
      else perBeam[cp.beam].time += mu / (dr / 60) + (cp.segs ? cp.segs.length * 1.5 : 0);
    }
    for (const k in perBeam) time += perBeam[k].time + 10;
    return { total, perBeam, minutes: time / 60, estimated: state.stage < 2 };
  }
  function stats(which) {
    const grid = which ? which.grid : (state.fine || state.grid), dose = which ? which.dose : grid.dose, plan = state.plan, rx = plan.rx;
    const dmax = Math.max(1.25 * rx, 1);
    const out = { grid: grid.h, dvh: {}, rx };
    for (const nm of CASE.names()) { const m = CASE.maskOf(nm); if (m) out.dvh[nm] = dvh(grid, dose, m, dmax); }
    const T = out.dvh[plan.target];
    if (T) {
      const d2 = T.Dp(2), d98 = T.Dp(98), d50 = T.Dp(50);
      const body = voxOf(grid, CASE.structs[0].bit, true), tm = CASE.maskOf(plan.target);
      let piv = 0, tvpiv = 0; for (let q = 0; q < body.length; q++) { const v = body[q]; if (dose[v] >= 0.95 * rx) { piv++; if (grid.tag[v] & tm) tvpiv++; } }
      Object.assign(out, { V90: T.Vd(0.9 * rx), V95: T.Vd(0.95 * rx), V100: T.Vd(rx), V107: T.Vd(1.07 * rx), D98: d98, D95: T.Dp(95), D50: d50, D2: d2,
        Dmean: T.mean, HI: (d2 - d98) / Math.max(d50, 1e-6), CI: piv && T.n ? tvpiv * tvpiv / (T.n * piv) : 0 });
    }
    out.Dmax = out.dvh[CASE.structs[0].id] ? out.dvh[CASE.structs[0].id].max : 0;
    out.mu = muInfo();
    return out;
  }
  function goalValue(st, goal) {
    const d = st.dvh[goal.struct]; if (!d || !d.n) return null;
    switch (goal.metric) {
      case "Dmean": return d.mean; case "Dmax": return d.max; case "Dmin": return d.min;
      case "D": return d.Dp(goal.x); case "V": return d.Vd(goal.x); case "HI": return st.HI; case "CI": return st.CI;
      case "MU": return st.mu.total;
    }
    return null;
  }
  // leaves to display for a control point: segment `si` if sequenced, else a preview from the fluence
  function leaves(cp, si = 0) {
    if (cp.segs && cp.segs.length) { const s = cp.segs[Math.min(si, cp.segs.length - 1)]; return { l: s.l, r: s.r, w: s.w, n: cp.segs.length, idx: Math.min(si, cp.segs.length - 1), preview: false }; }
    let mx = 0; for (const f of cp.Fs) mx = Math.max(mx, f);
    const l = new Float32Array(cp.nY), r = new Float32Array(cp.nY);
    for (let i = 0; i < cp.nY; i++) {
      let a = -1, b = -1; for (let j = 0; j < cp.nX; j++) if (cp.Fs[j * cp.nY + i] > 0.3 * mx) { if (a < 0) a = j; b = j; }
      if (a < 0) l[i] = r[i] = 0.5 * (cp.X1 + cp.X2); else { l[i] = cp.X1 + a * cp.binX; r[i] = cp.X1 + (b + 1) * cp.binX; }
    }
    return { l, r, w: mx, n: 1, idx: 0, preview: true };
  }

  // ---------------------------------------------------------------- plan files
  function packF(F) { let mx = 0; for (const f of F) mx = Math.max(mx, f); const q = new Uint8Array(F.length); for (let i = 0; i < F.length; i++) q[i] = Math.round(255 * F[i] / (mx || 1)); let s = ""; for (const b of q) s += String.fromCharCode(b); return { mx, d: btoa(s) }; }
  function unpackF(p, F) { const s = atob(p.d); for (let i = 0; i < F.length && i < s.length; i++) F[i] = s.charCodeAt(i) / 255 * p.mx; }
  function exportPlan(withFluence) {
    const plan = JSON.parse(JSON.stringify(state.plan, (k, v) => k.startsWith("_") ? undefined : v));
    const out = { format: "rt-planning-simulator-plan", version: 1, phantom: CASE.ph.id, plan, stage: state.stage, scale: state.scale, structures: CASE.exportStructs() };
    if (withFluence) out.fluence = state.cps.map(cp => ({ F: packF(cp.F), segs: cp.segs ? cp.segs.map(s => ({ l: Array.from(s.l, v => +v.toFixed(2)), r: Array.from(s.r, v => +v.toFixed(2)), w: s.w })) : null }));
    return out;
  }
  function importFluence(obj) {
    if (!obj.fluence || obj.fluence.length !== state.cps.length) return false;
    state.scale = obj.scale || state.scale;
    state.cps.forEach((cp, i) => {
      const f = obj.fluence[i]; unpackF(f.F, cp.F);
      cp.segs = f.segs ? f.segs.map(s => ({ l: Float32Array.from(s.l), r: Float32Array.from(s.r), w: s.w })) : null;
      if (cp.segs) deliverable(cp);
    });
    forward(state.cps, state.grid.dose); state.stage = obj.stage || 1; state.fine = null; state.version++;
    return true;
  }

  return { BIN, ENERGY, OBJ_TYPES, OBJ_HELP, state, setup, calculate, optimise, optimiseWeights, stage2, finalCalc, doseAt, doseFrom,
    sampleGrid, robust, stats, goalValue, leaves, project, kernel, muInfo, exportPlan, importFluence, arcSpan, buildGrid, computeEff, retag,
    voxOf, meanIn, evalObjectives, smooth, forward, backwardCP };
})();
