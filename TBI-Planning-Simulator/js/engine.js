/* TBI Planning Simulator — plan model, approximate dose engine and Monaco-style optimiser.
 * EDUCATIONAL MODEL: a simple ray-tracing kernel (TMR x inverse square x fluence, radiological depth
 * through body and lungs, sigmoid penumbra). It is not Monte Carlo and not commissioned for any linac. */
"use strict";
const ENG = (() => {
  const SAD = 100, UHALF = 20, BIN = 0.5;

  function defaultPlan() {
    return {
      name: "VMAT-TBI, 3 isocentres",
      rx: 12, fx: 6, maxDoseRate: 250, cpStep: 10, smoothing: "Medium",
      isos: [
        { name: "A", z: 15.5, lo: -15.5, hi: 15.5, arcs: 2 },
        { name: "B", z: 42.5, lo: -13.5, hi: 13.5, arcs: 2 },
        { name: "C", z: 72.0, lo: -18.0, hi: 18.0, arcs: 2 },
      ],
      objectives: [
        { on: true, struct: "PTV", type: "Target Penalty", dose: 12.0, extra: 95, weight: 1.0 },
        { on: true, struct: "PTV", type: "Quadratic Overdose", dose: 13.2, extra: 0.3, weight: 1.0 },
        { on: true, struct: "Lungs", type: "Parallel", dose: 8.0, extra: 55, weight: 1.0 },
        { on: true, struct: "Lungs", type: "Quadratic Overdose", dose: 10.0, extra: 0.5, weight: 0.5 },
        { on: true, struct: "Body", type: "Maximum Dose", dose: 14.4, extra: 0, weight: 1.0 },
        { on: false, struct: "Kidneys", type: "Quadratic Overdose", dose: 10.0, extra: 0.5, weight: 0.5 },
      ],
    };
  }

  // ---------------------------------------------------------------- control points
  function buildCPs(plan) {
    const cps = [];
    plan.isos.forEach((iso, ii) => {
      for (let a = 0; a < iso.arcs; a++) {
        const dir = a % 2 === 0 ? 1 : -1;             // arc 1 CW, arc 2 CCW
        const n = Math.round(360 / plan.cpStep);
        for (let k = 0; k < n; k++) {
          // CW: 181 -> 179 through 0 ; CCW: 179 -> 181
          let th = dir > 0 ? 180 + (k + 0.5) * plan.cpStep : 180 - (k + 0.5) * plan.cpStep;
          th = ((th % 360) + 360) % 360;
          const t = th * Math.PI / 180;
          const nu = Math.round(2 * UHALF / BIN), nw = Math.max(1, Math.round((iso.hi - iso.lo) / BIN));
          cps.push({ iso: ii, arc: a, dir, k, theta: th, s: Math.sin(t), c: Math.cos(t),
            sx: SAD * Math.sin(t), sy: -SAD * Math.cos(t), z0: iso.z, wlo: iso.lo, whi: iso.hi,
            nu, nw, bw: (iso.hi - iso.lo) / nw,
            F: new Float32Array(nu * nw).fill(1), Fs: new Float32Array(nu * nw).fill(1) });
        }
      }
    });
    return cps;
  }

  // ---------------------------------------------------------------- kernel
  function rayEllipse(sx, sy, dx, dy, cx, cy, a, b) {
    const ox = (sx - cx) / a, oy = (sy - cy) / b, ex = dx / a, ey = dy / b;
    const A = ex * ex + ey * ey, B = 2 * (ox * ex + oy * ey), C = ox * ox + oy * oy - 1;
    const D = B * B - 4 * A * C;
    if (D <= 0) return null;
    const r = Math.sqrt(D);
    return [(-B - r) / (2 * A), (-B + r) / (2 * A)];
  }
  // 6 MV-like tissue-maximum ratio with an exponential build-up region (dmax about 1.5 cm)
  function tmr(d) {
    if (d < 1.5) return 1 - 0.58 * Math.exp(-Math.max(0, d) / 0.45) - 0.02 * (1.5 - d) / 1.5;
    return Math.exp(-0.047 * (d - 1.5));
  }
  const sig = d => 1 / (1 + Math.exp(-d / 0.28));
  // returns K (dose per unit fluence) and BEV coordinates in out[]; false if outside the beam
  function kernel(cp, x, y, z, out) {
    const vx = x - cp.sx, vy = y - cp.sy;
    const a = -vx * cp.s + vy * cp.c;               // distance from source along the central axis
    if (a <= 1) return false;
    const mag = SAD / a;
    const u = (vx * cp.c + vy * cp.s) * mag;
    const w = (z - cp.z0) * mag;
    if (u < -UHALF - 1.2 || u > UHALF + 1.2 || w < cp.wlo - 1.2 || w > cp.whi + 1.2) return false;
    const edge = sig(u + UHALF) * sig(UHALF - u) * sig(w - cp.wlo) * sig(cp.whi - w);
    // radiological depth in the axial plane at z
    const [ba, bb] = PH.half(z);
    const dx = x - cp.sx, dy = y - cp.sy, len = Math.hypot(dx, dy);
    const rb = rayEllipse(cp.sx, cp.sy, dx, dy, 0, 0, ba, bb);
    if (!rb) return false;
    const t0 = rb[0];
    let depth = (1 - t0) * len;
    const L = PH.lungs(z);
    for (let i = 0; i < L.length; i++) {
      const e = L[i], rl = rayEllipse(cp.sx, cp.sy, dx, dy, e.cx, e.cy, e.a, e.b);
      if (rl) {
        const lo = Math.max(rl[0], t0), hi = Math.min(rl[1], 1);
        if (hi > lo) depth -= 0.75 * (hi - lo) * len;
      }
    }
    out[0] = u; out[1] = w; out[2] = tmr(depth) * mag * mag * edge;
    return true;
  }
  // nearest bin across the field (u), linear interpolation along the field length (w);
  // returns the lower bin index and writes the weight of the upper bin into _frac[0]
  const _frac = [0];
  function binIndex(cp, u, w) {
    let i = Math.floor((u + UHALF) / BIN);
    i = i < 0 ? 0 : i >= cp.nu ? cp.nu - 1 : i;
    let fj = (w - cp.wlo) / cp.bw - 0.5;
    if (cp.nw < 2) { _frac[0] = 0; return i; }
    fj = fj < 0 ? 0 : fj > cp.nw - 1.0001 ? cp.nw - 1.0001 : fj;
    const j = Math.floor(fj); _frac[0] = fj - j;
    return j * cp.nu + i;
  }
  function bilinear(cp, u, w) {
    const b = binIndex(cp, u, w), f = _frac[0], F = cp.Fs, b2 = b + cp.nu > F.length - 1 ? b : b + cp.nu;
    return F[b] * (1 - f) + F[b2] * f;
  }

  // fluence smoothing (penumbra / leaf transmission blur, separable 1-2-1)
  function smooth(cp, src, dst) {
    const n = cp.nu, m = cp.nw;
    if (!cp._tmp || cp._tmp.length !== n * m) cp._tmp = new Float32Array(n * m);
    const tmp = cp._tmp;
    for (let j = 0; j < m; j++) {
      const r = j * n;
      for (let i = 0; i < n; i++) {
        const a = src[r + (i > 0 ? i - 1 : 0)], b = src[r + i], c = src[r + (i < n - 1 ? i + 1 : i)];
        tmp[r + i] = 0.25 * a + 0.5 * b + 0.25 * c;
      }
    }
    // along the field length: wider kernel 1-2-3-2-1 (removes row-to-row banding the 1 cm dose grid cannot see)
    for (let j = 0; j < m; j++) {
      const r = j * n, c = k => (k < 0 ? 0 : k >= m ? m - 1 : k) * n;
      const r2 = c(j - 2), r1 = c(j - 1), s1 = c(j + 1), s2 = c(j + 2);
      for (let i = 0; i < n; i++) dst[r + i] = (tmp[r2 + i] + 2 * tmp[r1 + i] + 3 * tmp[r + i] + 2 * tmp[s1 + i] + tmp[s2 + i]) / 9;
    }
  }

  // ---------------------------------------------------------------- dose grid and influence
  function buildGrid(h) {
    const xs = [], ys = [], zs = [];
    for (let x = -17.5 + h / 2; x < 17.5; x += h) xs.push(x);
    for (let y = -11.5 + h / 2; y < 11.5; y += h) ys.push(y);
    for (let z = h / 2; z < PH.LENGTH; z += h) zs.push(z);
    const vx = [], vy = [], vz = [], tag = [];
    for (const z of zs) for (const y of ys) for (const x of xs) {
      if (!PH.inBody(x, y, z)) continue;
      let t = 1;                                     // body
      if (PH.inPTV(x, y, z)) t |= 2;
      const li = PH.lungIndex(x, y, z); if (li) t |= li === 1 ? 4 : 8;
      if (PH.kidneyIndex(x, y, z)) t |= 16;
      vx.push(x); vy.push(y); vz.push(z); tag.push(t);
    }
    return { h, n: vx.length, x: Float32Array.from(vx), y: Float32Array.from(vy), z: Float32Array.from(vz),
             tag: Uint8Array.from(tag), dose: new Float32Array(vx.length) };
  }
  const MASK = { Body: 1, PTV: 2, Lung_R: 4, Lung_L: 8, Lungs: 12, Kidneys: 16 };

  function buildInfluence(cps, grid) {
    const out = [0, 0, 0];
    for (const cp of cps) {
      const zlo = cp.z0 + cp.wlo * 1.25 - 2, zhi = cp.z0 + cp.whi * 1.25 + 2;
      const vi = [], bi = [], kk = [], ff = [];
      for (let v = 0; v < grid.n; v++) {
        const z = grid.z[v];
        if (z < zlo || z > zhi) continue;
        if (kernel(cp, grid.x[v], grid.y[v], z, out) && out[2] > 1e-4) {
          vi.push(v); bi.push(binIndex(cp, out[0], out[1])); ff.push(_frac[0]); kk.push(out[2]);
        }
      }
      cp.vi = Int32Array.from(vi); cp.bi = Int32Array.from(bi); cp.kk = Float32Array.from(kk); cp.ff = Float32Array.from(ff);
    }
  }

  function forward(cps, grid, scale) {
    const D = grid.dose; D.fill(0);
    for (const cp of cps) {
      smooth(cp, cp.F, cp.Fs);
      const vi = cp.vi, bi = cp.bi, kk = cp.kk, ff = cp.ff, Fs = cp.Fs, nu = cp.nu, last = Fs.length - 1;
      for (let q = 0; q < vi.length; q++) {
        const b = bi[q], f = ff[q], b2 = b + nu > last ? b : b + nu;
        D[vi[q]] += (Fs[b] * (1 - f) + Fs[b2] * f) * kk[q];
      }
    }
    for (let v = 0; v < grid.n; v++) D[v] *= scale;
  }

  // ---------------------------------------------------------------- objectives
  function evalObjectives(plan, grid, g) {
    g.fill(0);
    let total = 0;
    const D = grid.dose, terms = [];
    for (const ob of plan.objectives) {
      if (!ob.on) continue;
      const m = MASK[ob.struct];
      let n = 0;
      for (let v = 0; v < grid.n; v++) if (grid.tag[v] & m) n++;
      if (!n) continue;
      let f = 0;
      if (ob.type === "Target Penalty") {
        // drive the dose to the prescription, extra penalty for underdose
        const lo = ob.dose * 0.95;
        for (let v = 0; v < grid.n; v++) if (grid.tag[v] & m) {
          const d = D[v], e = d - ob.dose, u = Math.min(0, d - lo);
          f += 0.3 * e * e + 6 * u * u;
          g[v] += ob.weight * (0.6 * e + 12 * u) / n;
        }
      } else if (ob.type === "Quadratic Overdose" || ob.type === "Maximum Dose") {
        const k = ob.type === "Maximum Dose" ? 20 : 4;
        for (let v = 0; v < grid.n; v++) if (grid.tag[v] & m) {
          const e = Math.max(0, D[v] - ob.dose);
          f += k * e * e; g[v] += ob.weight * 2 * k * e / n;
        }
      } else if (ob.type === "Parallel") {
        // mean organ damage with a power-law response; target = extra (%)
        const ref = ob.dose, p = 4, target = ob.extra / 100;
        let mod = 0;
        if (!grid._dd) grid._dd = new Float32Array(grid.n);
        const dd = grid._dd;
        for (let v = 0; v < grid.n; v++) if (grid.tag[v] & m) {
          const r = Math.pow(Math.max(D[v], 1e-3) / ref, p), dam = r / (1 + r);
          mod += dam; dd[v] = p * r / ((1 + r) * (1 + r) * Math.max(D[v], 1e-3));
        }
        mod /= n;
        const ex = Math.max(0, mod - target);
        f = 400 * ex * ex;
        if (ex > 0) for (let v = 0; v < grid.n; v++) if (grid.tag[v] & m) g[v] += ob.weight * 800 * ex * dd[v] / n;
        ob._mod = mod;
      }
      f = ob.weight * f / (ob.type === "Parallel" ? 1 : n);
      ob._value = f; total += f; terms.push(f);
    }
    return total;
  }

  function backward(cps, grid, g, scale, grads) {
    for (let c = 0; c < cps.length; c++) {
      const cp = cps[c], G = grads[c]; G.fill(0);
      const vi = cp.vi, bi = cp.bi, kk = cp.kk, ff = cp.ff, nu = cp.nu, last = G.length - 1;
      for (let q = 0; q < vi.length; q++) {
        const b = bi[q], f = ff[q], b2 = b + nu > last ? b : b + nu, gk = g[vi[q]] * kk[q] * scale;
        G[b] += gk * (1 - f); G[b2] += gk * f;
      }
      if (!cp._g2 || cp._g2.length !== G.length) cp._g2 = new Float32Array(G.length);
      smooth(cp, G, cp._g2); G.set(cp._g2);
    }
  }

  function meanIn(grid, mask) {
    let s = 0, n = 0;
    for (let v = 0; v < grid.n; v++) if (grid.tag[v] & mask) { s += grid.dose[v]; n++; }
    return n ? s / n : 0;
  }

  // ---------------------------------------------------------------- state and optimisation
  const state = { plan: defaultPlan(), cps: [], grid: null, scale: 1, optimised: false, history: [], fine: null };

  function setup(plan) {
    state.plan = plan || state.plan;
    state.cps = buildCPs(state.plan);
    if (!state.grid) state.grid = buildGrid(1.0);
    buildInfluence(state.cps, state.grid);
    // initial open arcs, scaled to the prescription
    state.scale = 1; forward(state.cps, state.grid, 1);
    state.scale = state.plan.rx / meanIn(state.grid, MASK.PTV);
    forward(state.cps, state.grid, state.scale);
    state.optimised = false; state.history = []; state.fine = null;
  }

  const SMOOTH_W = { Off: 0, Low: 0.0003, Medium: 0.0008, High: 0.003 };

  // run the optimiser in chunks; onStep(iter, total, objective) lets the UI update
  function optimise(nIter, onStep, onDone) {
    const cps = state.cps, grid = state.grid, plan = state.plan;
    const g = new Float32Array(grid.n);
    const grads = cps.map(cp => new Float32Array(cp.F.length));
    const m1 = cps.map(cp => new Float32Array(cp.F.length)), m2 = cps.map(cp => new Float32Array(cp.F.length));
    const lr = plan._lr || 0.06, b1 = 0.9, b2 = 0.999, sw = SMOOTH_W[plan.smoothing] ?? 0.0008;
    let it = 0;
    function step() {
      const t0 = performance.now();
      while (it < nIter && performance.now() - t0 < 40) {
        forward(cps, grid, state.scale);
        // keep the mean PTV dose at the prescription (normalisation as in the thesis plan)
        const mp = meanIn(grid, MASK.PTV);
        if (mp > 0) {
          const f = plan.rx / mp; state.scale *= f;
          for (let v = 0; v < grid.n; v++) grid.dose[v] *= f;
        }
        const obj = evalObjectives(plan, grid, g);
        backward(cps, grid, g, state.scale, grads);
        it++;
        const c1 = 1 / (1 - Math.pow(b1, it)), c2 = 1 / (1 - Math.pow(b2, it));
        const lrt = lr * (0.25 + 0.75 * Math.max(0, 1 - it / nIter));   // decaying step
        for (let c = 0; c < cps.length; c++) {
          const cp = cps[c], F = cp.F, G = grads[c], M = m1[c], V = m2[c], n = cp.nu;
          for (let q = 0; q < F.length; q++) {
            // fluence smoothing penalty (Monaco "fluence smoothing" analogue)
            const i = q % n, lap = (i > 0 ? F[q] - F[q - 1] : 0) + (i < n - 1 ? F[q] - F[q + 1] : 0);
            const gr = G[q] + sw * lap;
            M[q] = b1 * M[q] + (1 - b1) * gr; V[q] = b2 * V[q] + (1 - b2) * gr * gr;
            const f = F[q] - lrt * (M[q] * c1) / (Math.sqrt(V[q] * c2) + 1e-8);
            F[q] = f < 0 ? 0 : f > 6 ? 6 : f;
          }
        }
        state.history.push(obj);
      }
      if (it >= nIter) {
        forward(cps, grid, state.scale);
        const mp = meanIn(grid, MASK.PTV);
        if (mp > 0) { state.scale *= plan.rx / mp; forward(cps, grid, state.scale); }
      }
      if (onStep) onStep(it, nIter, state.history[state.history.length - 1]);
      if (it < nIter) requestAnimationFrame(step);
      else { state.optimised = true; state.fine = null; if (onDone) onDone(); }
    }
    requestAnimationFrame(step);
  }

  // dose at an arbitrary point (bilinear fluence), course dose in Gy
  const _o = [0, 0, 0];
  function doseAt(x, y, z) {
    if (!PH.inBody(x, y, z)) return 0;
    let d = 0;
    for (const cp of state.cps) {
      const zlo = cp.z0 + cp.wlo * 1.25 - 2, zhi = cp.z0 + cp.whi * 1.25 + 2;
      if (z < zlo || z > zhi) continue;
      if (kernel(cp, x, y, z, _o)) d += bilinear(cp, _o[0], _o[1]) * _o[2];
    }
    return d * state.scale;
  }

  // fine 0.5 cm calculation for the DVH (chunked)
  function finalCalc(onStep, onDone) {
    const grid = buildGrid(0.5);
    let v = 0;
    function step() {
      const t0 = performance.now();
      while (v < grid.n && performance.now() - t0 < 40) { grid.dose[v] = doseAt(grid.x[v], grid.y[v], grid.z[v]); v++; }
      if (onStep) onStep(v, grid.n);
      if (v < grid.n) requestAnimationFrame(step); else { state.fine = grid; if (onDone) onDone(); }
    }
    requestAnimationFrame(step);
  }

  // ---------------------------------------------------------------- evaluation
  function dvh(grid, mask, dmax = 16, nb = 320) {
    const vals = [];
    for (let v = 0; v < grid.n; v++) if (grid.tag[v] & mask) vals.push(grid.dose[v]);
    vals.sort((a, b) => a - b);
    const curve = [];
    for (let i = 0; i <= nb; i++) {
      const d = dmax * i / nb;
      let lo = 0, hi = vals.length;
      while (lo < hi) { const mid = (lo + hi) >> 1; if (vals[mid] < d) lo = mid + 1; else hi = mid; }
      curve.push([d, vals.length ? 100 * (vals.length - lo) / vals.length : 0]);
    }
    const Dp = p => vals.length ? vals[Math.min(vals.length - 1, Math.max(0, Math.floor((1 - p / 100) * vals.length)))] : 0;
    const Vd = d => { let c = 0; for (const x of vals) if (x >= d) c++; return vals.length ? 100 * c / vals.length : 0; };
    const mean = vals.reduce((a, b) => a + b, 0) / Math.max(1, vals.length);
    return { curve, mean, Dp, Vd, max: vals[vals.length - 1] || 0, n: vals.length };
  }

  function stats() {
    const grid = state.fine || state.grid, rx = state.plan.rx;
    const ptv = dvh(grid, MASK.PTV), lungs = dvh(grid, MASK.Lungs), body = dvh(grid, MASK.Body), kid = dvh(grid, MASK.Kidneys);
    const lr = dvh(grid, MASK.Lung_R), ll = dvh(grid, MASK.Lung_L);
    const d2 = ptv.Dp(2), d98 = ptv.Dp(98), d50 = ptv.Dp(50);
    // MU estimate: peak fluence per control point converted to cGy per fraction at dmax
    let mu = 0; const muArc = {};
    for (const cp of state.cps) {
      let mx = 0; for (const f of cp.Fs) mx = Math.max(mx, f);
      const m = mx * state.scale * 100 / state.plan.fx;
      mu += m; const key = state.plan.isos[cp.iso].name + (cp.arc + 1);
      muArc[key] = (muArc[key] || 0) + m;
    }
    let beamOn = 0;
    for (const k in muArc) beamOn += Math.max(muArc[k] / state.plan.maxDoseRate, 1.0);
    return { grid: grid === state.fine ? "0.5 cm" : "1.0 cm", V90: ptv.Vd(0.9 * rx), V95: ptv.Vd(0.95 * rx),
      D98: d98, D50: d50, D2: d2, Dmean: ptv.mean, HI: (d2 - d98) / Math.max(d50, 1e-6), Dmax: body.max,
      lungMean: lungs.mean, lungR: lr.mean, lungL: ll.mean, lungV8: lungs.Vd(8), lungV10: lungs.Vd(10), lungV12: lungs.Vd(12),
      kidneyMean: kid.mean, MU: mu, muArc, beamOn, dvh: { PTV: ptv, Lungs: lungs, Lung_R: lr, Lung_L: ll, Kidneys: kid, Body: body } };
  }

  // leaf positions for a control point (pairs of 0.5 cm across u; leaves travel along w)
  function leaves(cp, thr = 0.25) {
    let mx = 0; for (const f of cp.Fs) mx = Math.max(mx, f);
    const pairs = [];
    for (let p = 0; p < 80; p++) {
      const u = -UHALF + 0.25 + p * 0.5, i = Math.min(cp.nu - 1, Math.floor((u + UHALF) / BIN));
      let a = null, b = null;
      for (let j = 0; j < cp.nw; j++) {
        if (cp.Fs[j * cp.nu + i] > thr * mx) { if (a === null) a = j; b = j; }
      }
      if (a === null) { const mid = (cp.wlo + cp.whi) / 2; pairs.push([u, mid, mid]); }
      else pairs.push([u, cp.wlo + a * cp.bw, cp.wlo + (b + 1) * cp.bw]);
    }
    return { pairs, max: mx };
  }

  return { SAD, UHALF, BIN, defaultPlan, setup, optimise, finalCalc, doseAt, stats, leaves, kernel, state, MASK, meanIn };
})();
