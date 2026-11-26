/* TBI Planning Simulator — 2D views: axial, coronal, sagittal, beam's-eye view, DVH and profile. */
"use strict";
const V2 = (() => {
  const ISO_LEVELS = [
    { p: 110, c: "#ff2d55" }, { p: 105, c: "#ff8c1a" }, { p: 100, c: "#ffe14d" }, { p: 95, c: "#4cd964" },
    { p: 90, c: "#2ec5ff" }, { p: 80, c: "#3d7bff" }, { p: 50, c: "#b46bff" },
  ];
  const ISO_COL = ["#58a6ff", "#ff9f43", "#3ddc97", "#ff6b9a", "#c9a0ff"];

  // ------------------------------------------------------------ helpers
  function fitCanvas(cv) {
    const dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
    if (cv.width !== Math.round(W * dpr) || cv.height !== Math.round(H * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
    const g = cv.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { g, W, H };
  }
  // marching squares: values[ny][nx] sampled at (x0 + i*dx, y0 + j*dy); returns segments in world coords
  function contour(vals, nx, ny, x0, y0, dx, dy, lev) {
    const segs = [];
    const P = (i, j) => vals[j * nx + i];
    for (let j = 0; j < ny - 1; j++) for (let i = 0; i < nx - 1; i++) {
      const a = P(i, j), b = P(i + 1, j), c = P(i + 1, j + 1), d = P(i, j + 1);
      let k = 0; if (a >= lev) k |= 1; if (b >= lev) k |= 2; if (c >= lev) k |= 4; if (d >= lev) k |= 8;
      if (k === 0 || k === 15) continue;
      const X = x0 + i * dx, Y = y0 + j * dy;
      const e = [
        [X + dx * (lev - a) / (b - a), Y], [X + dx, Y + dy * (lev - b) / (c - b)],
        [X + dx * (lev - d) / (c - d), Y + dy], [X, Y + dy * (lev - a) / (d - a)]];
      const T = { 1: [[3, 0]], 2: [[0, 1]], 3: [[3, 1]], 4: [[1, 2]], 5: [[3, 0], [1, 2]], 6: [[0, 2]], 7: [[3, 2]],
        8: [[2, 3]], 9: [[0, 2]], 10: [[0, 1], [2, 3]], 11: [[1, 2]], 12: [[1, 3]], 13: [[0, 1]], 14: [[0, 3]] }[k];
      for (const [p, q] of T) segs.push([e[p][0], e[p][1], e[q][0], e[q][1]]);
    }
    return segs;
  }
  function washColor(f) { // f = dose / rx
    const stops = [[0.3, [40, 40, 200]], [0.5, [60, 110, 255]], [0.8, [40, 200, 230]], [0.9, [60, 220, 120]],
                   [0.95, [190, 235, 60]], [1.0, [255, 220, 40]], [1.05, [255, 140, 20]], [1.12, [240, 30, 40]]];
    if (f < stops[0][0]) return null;
    for (let i = 1; i < stops.length; i++) if (f <= stops[i][0]) {
      const t = (f - stops[i - 1][0]) / (stops[i][0] - stops[i - 1][0]), a = stops[i - 1][1], b = stops[i][1];
      return [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), a[2] + t * (b[2] - a[2])];
    }
    return stops[stops.length - 1][1];
  }
  function label(g, x, y, t, col = "#cfd8e3", align = "left", font = "11px system-ui, sans-serif") {
    g.font = font; g.textAlign = align; g.fillStyle = "rgba(0,0,0,0.55)"; g.fillText(t, x + 1, y + 1); g.fillStyle = col; g.fillText(t, x, y);
  }

  // ------------------------------------------------------------ slice views
  // kind: "axial" (x horiz, y vert), "coronal" (x horiz, z vert), "sagittal" (y horiz, z vert)
  function SliceView(cv, kind) {
    this.cv = cv; this.kind = kind; this.cache = {}; this.zoom = 1; this.pan = [0, 0];
  }
  SliceView.prototype.extent = function () {
    if (this.kind === "axial") return { u0: -19, u1: 19, v0: -13, v1: 13 };
    if (this.kind === "coronal") return { u0: -19, u1: 19, v0: -3, v1: PH.LENGTH + 3 };
    return { u0: -14, u1: 14, v0: -3, v1: PH.LENGTH + 3 };
  };
  // world point for (u, v) given the crosshair
  SliceView.prototype.world = function (u, v, X) {
    if (this.kind === "axial") return [u, v, X.z];
    if (this.kind === "coronal") return [u, X.y, v];
    return [X.x, u, v];
  };
  SliceView.prototype.map = function (W, H) {
    const e = this.extent(), sx = W / (e.u1 - e.u0), sy = H / (e.v1 - e.v0), s = Math.min(sx, sy) * this.zoom;
    const ox = W / 2 - s * (e.u0 + e.u1) / 2 + this.pan[0], oy = H / 2 - s * (e.v0 + e.v1) / 2 + this.pan[1];
    return { s, ox, oy, X: u => ox + u * s, Y: v => oy + v * s, U: px => (px - ox) / s, V: py => (py - oy) / s };
  };
  SliceView.prototype.sliceKey = function (X) { return this.kind === "axial" ? X.z : this.kind === "coronal" ? X.y : X.x; };

  SliceView.prototype.ctImage = function (X, win) {
    const key = "ct" + this.sliceKey(X).toFixed(2) + win.c + win.w;
    if (this.cache.ctKey === key) return this.cache.ct;
    const e = this.extent(), h = this.kind === "axial" ? 0.15 : 0.25;
    const nx = Math.round((e.u1 - e.u0) / h), ny = Math.round((e.v1 - e.v0) / h);
    const cv = document.createElement("canvas"); cv.width = nx; cv.height = ny;
    const g = cv.getContext("2d"), img = g.createImageData(nx, ny);
    const lo = win.c - win.w / 2;
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      const [x, y, z] = this.world(e.u0 + (i + 0.5) * h, e.v0 + (j + 0.5) * h, X);
      const v = Math.max(0, Math.min(255, (PH.hu(x, y, z, this.kind === "axial") - lo) / win.w * 255));
      const o = 4 * (j * nx + i); img.data[o] = v; img.data[o + 1] = v; img.data[o + 2] = v; img.data[o + 3] = 255;
    }
    g.putImageData(img, 0, 0);
    this.cache.ctKey = key; this.cache.ct = { cv, e };
    return this.cache.ct;
  };
  SliceView.prototype.structSegs = function (X) {
    const key = "st" + this.sliceKey(X).toFixed(2);
    if (this.cache.stKey === key) return this.cache.st;
    const e = this.extent(), h = 0.25, nx = Math.round((e.u1 - e.u0) / h) + 1, ny = Math.round((e.v1 - e.v0) / h) + 1;
    const out = {};
    for (const s of PH.STRUCTS) {
      if (s.dvhOnly) continue;
      const vals = new Float32Array(nx * ny);
      for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
        const [x, y, z] = this.world(e.u0 + i * h, e.v0 + j * h, X);
        vals[j * nx + i] = s.test(x, y, z) ? 1 : 0;
      }
      out[s.id] = contour(vals, nx, ny, e.u0, e.v0, h, h, 0.5);
    }
    this.cache.stKey = key; this.cache.st = out;
    return out;
  };
  SliceView.prototype.doseGrid = function (X, version) {
    const key = "d" + this.sliceKey(X).toFixed(2) + "_" + version;
    if (this.cache.dKey === key) return this.cache.d;
    const e = this.extent(), h = this.kind === "axial" ? 0.4 : 0.5;
    const nx = Math.round((e.u1 - e.u0) / h) + 1, ny = Math.round((e.v1 - e.v0) / h) + 1;
    const vals = new Float32Array(nx * ny);
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      const [x, y, z] = this.world(e.u0 + i * h, e.v0 + j * h, X);
      vals[j * nx + i] = ENG.doseAt(x, y, z);
    }
    this.cache.dKey = key; this.cache.d = { vals, nx, ny, h, e };
    return this.cache.d;
  };

  SliceView.prototype.draw = function (S) {
    const { g, W, H } = fitCanvas(this.cv), m = this.map(W, H), X = S.cross, rx = ENG.state.plan.rx;
    g.fillStyle = "#000"; g.fillRect(0, 0, W, H);
    // CT
    const ct = this.ctImage(X, S.window);
    g.imageSmoothingEnabled = true;
    g.drawImage(ct.cv, m.X(ct.e.u0), m.Y(ct.e.v0), (ct.e.u1 - ct.e.u0) * m.s, (ct.e.v1 - ct.e.v0) * m.s);
    // dose
    if (S.doseMode !== "none") {
      const d = this.doseGrid(X, S.doseVersion);
      if (S.doseMode === "wash") {
        const cv = document.createElement("canvas"); cv.width = d.nx; cv.height = d.ny;
        const cg = cv.getContext("2d"), img = cg.createImageData(d.nx, d.ny);
        for (let q = 0; q < d.vals.length; q++) {
          const c = washColor(d.vals[q] / rx);
          if (c) { img.data[4 * q] = c[0]; img.data[4 * q + 1] = c[1]; img.data[4 * q + 2] = c[2]; img.data[4 * q + 3] = 120; }
        }
        cg.putImageData(img, 0, 0);
        g.drawImage(cv, m.X(d.e.u0 - d.h / 2), m.Y(d.e.v0 - d.h / 2), d.nx * d.h * m.s, d.ny * d.h * m.s);
      } else {
        g.lineWidth = 1.3;
        for (const L of ISO_LEVELS) {
          if (!S.isoLevels[L.p]) continue;
          const segs = contour(d.vals, d.nx, d.ny, d.e.u0, d.e.v0, d.h, d.h, rx * L.p / 100);
          g.strokeStyle = L.c; g.beginPath();
          for (const s of segs) { g.moveTo(m.X(s[0]), m.Y(s[1])); g.lineTo(m.X(s[2]), m.Y(s[3])); }
          g.stroke();
        }
      }
    }
    // structures
    const st = this.structSegs(X);
    g.lineWidth = 1.4;
    for (const s of PH.STRUCTS) {
      if (s.dvhOnly || !S.showStruct[s.id]) continue;
      g.strokeStyle = s.color; g.beginPath();
      for (const q of st[s.id]) { g.moveTo(m.X(q[0]), m.Y(q[1])); g.lineTo(m.X(q[2]), m.Y(q[3])); }
      g.stroke();
    }
    this.drawBeams(g, m, S);
    // crosshair
    g.strokeStyle = "rgba(255,230,90,0.55)"; g.lineWidth = 1; g.setLineDash([4, 4]); g.beginPath();
    if (this.kind === "axial") { g.moveTo(m.X(X.x), 0); g.lineTo(m.X(X.x), H); g.moveTo(0, m.Y(X.y)); g.lineTo(W, m.Y(X.y)); }
    else if (this.kind === "coronal") { g.moveTo(m.X(X.x), 0); g.lineTo(m.X(X.x), H); g.moveTo(0, m.Y(X.z)); g.lineTo(W, m.Y(X.z)); }
    else { g.moveTo(m.X(X.y), 0); g.lineTo(m.X(X.y), H); g.moveTo(0, m.Y(X.z)); g.lineTo(W, m.Y(X.z)); }
    g.stroke(); g.setLineDash([]);
    // labels and orientation
    const title = { axial: `Axial  z = ${X.z.toFixed(1)} cm`, coronal: `Coronal  y = ${X.y.toFixed(1)} cm`, sagittal: `Sagittal  x = ${X.x.toFixed(1)} cm` }[this.kind];
    label(g, 8, 16, title, "#e8eef5", "left", "600 12px system-ui, sans-serif");
    const dv = ENG.doseAt(X.x, X.y, X.z);
    label(g, 8, 32, `Dose at cursor: ${dv.toFixed(2)} Gy (${(100 * dv / rx).toFixed(1)}%)`, "#9fb3c8");
    const o = { axial: ["R", "L", "A", "P"], coronal: ["R", "L", "H", "F"], sagittal: ["A", "P", "H", "F"] }[this.kind];
    label(g, 6, H / 2, o[0], "#ffd75e"); label(g, W - 14, H / 2, o[1], "#ffd75e");
    label(g, W / 2, 14, o[2], "#ffd75e", "center"); label(g, W / 2, H - 6, o[3], "#ffd75e", "center");
    // scale bar 10 cm
    g.strokeStyle = "#cfd8e3"; g.lineWidth = 2; g.beginPath(); g.moveTo(W - 14 - 10 * m.s, H - 14); g.lineTo(W - 14, H - 14); g.stroke();
    label(g, W - 14 - 5 * m.s, H - 18, "10 cm", "#cfd8e3", "center");
    this._m = m;
  };

  SliceView.prototype.drawBeams = function (g, m, S) {
    const plan = ENG.state.plan, cp = S.cp;
    if (this.kind === "axial") {
      if (!S.showBeams || !cp) return;
      // spokes of the current arc (beam track) and the current beam
      const ci = plan.isos[cp.iso];
      const within = S.cross.z > ci.z + ci.lo - 3 && S.cross.z < ci.z + ci.hi + 3;
      g.lineWidth = 1;
      for (const c of ENG.state.cps) {
        if (c.iso !== cp.iso || c.arc !== cp.arc) continue;
        g.strokeStyle = "rgba(255,170,60,0.18)"; g.beginPath(); g.moveTo(m.X(c.sx * 0.3), m.Y(c.sy * 0.3)); g.lineTo(m.X(0), m.Y(0)); g.stroke();
      }
      const S0 = [cp.sx, cp.sy], ext = 140;
      const dirx = -cp.s, diry = cp.c, ux = cp.c, uy = cp.s;
      const end = (u) => [cp.sx + ext * dirx + u * 1.4 * ux, cp.sy + ext * diry + u * 1.4 * uy];
      g.fillStyle = within ? "rgba(255,140,30,0.05)" : "rgba(160,160,160,0.03)";
      const e1 = end(-20), e2 = end(20);
      g.beginPath(); g.moveTo(m.X(S0[0]), m.Y(S0[1])); g.lineTo(m.X(e1[0]), m.Y(e1[1])); g.lineTo(m.X(e2[0]), m.Y(e2[1])); g.closePath(); g.fill();
      g.strokeStyle = within ? "rgba(255,160,60,0.85)" : "rgba(170,170,170,0.5)"; g.lineWidth = 1.2;
      g.beginPath(); g.moveTo(m.X(S0[0]), m.Y(S0[1])); g.lineTo(m.X(e1[0]), m.Y(e1[1])); g.moveTo(m.X(S0[0]), m.Y(S0[1])); g.lineTo(m.X(e2[0]), m.Y(e2[1])); g.stroke();
      g.setLineDash([6, 4]); g.beginPath(); g.moveTo(m.X(S0[0]), m.Y(S0[1])); const ce = end(0); g.lineTo(m.X(ce[0]), m.Y(ce[1])); g.stroke(); g.setLineDash([]);
      // gantry angle label near the beam entrance
      const lp = [cp.sx * 0.16, cp.sy * 0.16];
      label(g, m.X(lp[0]), m.Y(lp[1]), `G ${cp.theta.toFixed(0)}°`, "#ffb35c", "center", "600 11px system-ui, sans-serif");
      g.fillStyle = "#ff5a4f"; g.beginPath(); g.arc(m.X(0), m.Y(0), 3, 0, 7); g.fill();
      return;
    }
    // coronal / sagittal: jaw-defined field lengths, overlaps and isocentres
    const halfW = this.kind === "coronal" ? 20 : 13;
    plan.isos.forEach((iso, i) => {
      const col = ISO_COL[i % ISO_COL.length], cur = cp && cp.iso === i;
      g.strokeStyle = col; g.lineWidth = cur ? 2.2 : 1.2; g.setLineDash(cur ? [] : [6, 4]);
      g.strokeRect(m.X(-halfW + i * 0.4), m.Y(iso.z + iso.lo), m.s * (2 * halfW - i * 0.8), m.s * (iso.hi - iso.lo));
      g.setLineDash([]);
      g.fillStyle = col; g.beginPath(); g.arc(m.X(0), m.Y(iso.z), 3.5, 0, 7); g.fill();
      label(g, m.X(halfW) - 4, m.Y(iso.z) - 4, `Iso ${iso.name}`, col, "right", "600 11px system-ui, sans-serif");
    });
    for (let i = 0; i < plan.isos.length - 1; i++) {
      const a = plan.isos[i], b = plan.isos[i + 1], z1 = b.z + b.lo, z2 = a.z + a.hi;
      if (z2 > z1) {
        g.fillStyle = "rgba(255,255,255,0.10)"; g.fillRect(m.X(-halfW), m.Y(z1), 2 * halfW * m.s, (z2 - z1) * m.s);
        label(g, m.X(-halfW) + 4, m.Y((z1 + z2) / 2) + 4, `overlap ${(z2 - z1).toFixed(1)} cm`, "#e8eef5");
      } else {
        g.fillStyle = "rgba(255,60,60,0.25)"; g.fillRect(m.X(-halfW), m.Y(z2), 2 * halfW * m.s, (z1 - z2) * m.s);
        label(g, m.X(-halfW) + 4, m.Y((z1 + z2) / 2) + 4, `GAP ${(z1 - z2).toFixed(1)} cm`, "#ff6b6b");
      }
    }
  };

  // ------------------------------------------------------------ beam's-eye view
  function BEV(cv) { this.cv = cv; this.cache = {}; }
  BEV.prototype.project = function (cp, pts3) {
    const out = [0, 0, 0], res = [];
    for (const [x, y, z] of pts3) {
      const vx = x - cp.sx, vy = y - cp.sy, a = -vx * cp.s + vy * cp.c, mag = ENG.SAD / a;
      res.push([(vx * cp.c + vy * cp.s) * mag, (z - cp.z0) * mag]);
    }
    return res;
  };
  // silhouette of an elliptic structure set: for each z, the min/max projected u
  BEV.prototype.silhouette = function (cp, ellipsesAt, z0, z1) {
    const left = [], right = [];
    for (let z = z0; z <= z1; z += 0.5) {
      const E = ellipsesAt(z); if (!E.length) continue;
      for (const e of E) {
        const pts = [];
        for (let i = 0; i < 36; i++) { const t = i / 36 * 2 * Math.PI; pts.push([e.cx + e.a * Math.cos(t), e.cy + e.b * Math.sin(t), z]); }
        const p = this.project(cp, pts);
        let mn = 1e9, mx = -1e9, w = 0;
        for (const q of p) { mn = Math.min(mn, q[0]); mx = Math.max(mx, q[0]); w += q[1]; }
        (e.key ? (left[e.key] = left[e.key] || [], left[e.key]) : left).push([mn, w / p.length]);
        (e.key ? (right[e.key] = right[e.key] || [], right[e.key]) : right).push([mx, w / p.length]);
      }
    }
    return { left, right };
  };
  BEV.prototype.draw = function (S) {
    const { g, W, H } = fitCanvas(this.cv), cp = S.cp;
    g.fillStyle = "#05070a"; g.fillRect(0, 0, W, H);
    if (!cp) return;
    const wr0 = Math.min(cp.wlo, -20) - 2, wr1 = Math.max(cp.whi, 20) + 2;
    const s = Math.min(W / 46, H / (wr1 - wr0)), ox = W / 2, oy = H / 2 - s * (wr0 + wr1) / 2;
    const X = u => ox + u * s, Y = w => oy + w * s;
    // fluence of this control point
    const Fm = ENG.leaves(cp).max || 1;
    for (let j = 0; j < cp.nw; j++) for (let i = 0; i < cp.nu; i++) {
      const f = cp.Fs[j * cp.nu + i] / Fm;
      g.fillStyle = `rgba(${Math.round(255 * Math.min(1, f * 1.4))},${Math.round(200 * f)},${Math.round(60 + 80 * f)},${0.15 + 0.6 * f})`;
      g.fillRect(X(-20 + i * ENG.BIN), Y(cp.wlo + j * cp.bw), ENG.BIN * s + 0.5, cp.bw * s + 0.5);
    }
    // projected structures
    const body = this.silhouette(cp, z => { const [a, b] = PH.half(z); return [{ cx: 0, cy: 0, a, b }]; }, Math.max(0.5, cp.z0 + wr0 * 0.9), Math.min(PH.LENGTH - 0.5, cp.z0 + wr1 * 0.9));
    const lungs = this.silhouette(cp, z => PH.lungs(z).map((e, i) => ({ ...e, key: i ? "L" : "R" })), cp.z0 + wr0, cp.z0 + wr1);
    const poly = (L, R, col, fill) => {
      if (!L || !L.length) return;
      g.beginPath(); g.moveTo(X(L[0][0]), Y(L[0][1]));
      for (const p of L) g.lineTo(X(p[0]), Y(p[1]));
      for (let i = R.length - 1; i >= 0; i--) g.lineTo(X(R[i][0]), Y(R[i][1]));
      g.closePath(); if (fill) { g.fillStyle = fill; g.fill(); } g.strokeStyle = col; g.lineWidth = 1.5; g.stroke();
    };
    poly(body.left, body.right, "#7fdc7f");
    poly(lungs.left.R, lungs.right.R, "#4fa3ff", "rgba(79,163,255,0.12)");
    poly(lungs.left.L, lungs.right.L, "#a07bff", "rgba(160,123,255,0.12)");
    // MLC (Agility-like, 80 pairs of 0.5 cm, leaves travel along w with collimator 90°)
    if (S.showMLC) {
      const lv = ENG.leaves(cp);
      for (const [u, a, b] of lv.pairs) {
        g.fillStyle = "rgba(120,135,155,0.78)"; g.strokeStyle = "rgba(20,25,30,0.9)"; g.lineWidth = 0.5;
        if (a > cp.wlo - 0.01) { g.fillRect(X(u - 0.25), Y(cp.wlo - 1.5), 0.5 * s, (a - cp.wlo + 1.5) * s); g.strokeRect(X(u - 0.25), Y(cp.wlo - 1.5), 0.5 * s, (a - cp.wlo + 1.5) * s); }
        if (b < cp.whi + 0.01) { g.fillRect(X(u - 0.25), Y(b), 0.5 * s, (cp.whi + 1.5 - b) * s); g.strokeRect(X(u - 0.25), Y(b), 0.5 * s, (cp.whi + 1.5 - b) * s); }
      }
    }
    // jaws
    g.strokeStyle = "#ffd75e"; g.lineWidth = 2; g.strokeRect(X(-20), Y(cp.wlo), 40 * s, (cp.whi - cp.wlo) * s);
    // graticule
    g.strokeStyle = "rgba(255,255,255,0.35)"; g.lineWidth = 1; g.beginPath();
    g.moveTo(X(-22), Y(0)); g.lineTo(X(22), Y(0)); g.moveTo(X(0), Y(wr0)); g.lineTo(X(0), Y(wr1)); g.stroke();
    for (let t = -20; t <= 20; t += 5) { g.beginPath(); g.moveTo(X(t), Y(0) - 3); g.lineTo(X(t), Y(0) + 3); g.stroke(); }
    const iso = ENG.state.plan.isos[cp.iso];
    label(g, 8, 16, `BEV  Iso ${iso.name} · Arc ${cp.arc + 1} (${cp.dir > 0 ? "CW" : "CCW"})`, "#e8eef5", "left", "600 12px system-ui, sans-serif");
    label(g, 8, 32, `Gantry ${cp.theta.toFixed(1)}° · Coll 90° · Couch 0°`, "#ffb35c");
    label(g, 8, 48, `Jaws: X ±20.0 · Y ${cp.wlo.toFixed(1)} / ${cp.whi.toFixed(1)} cm`, "#9fb3c8");
    label(g, W - 8, H - 8, "head ↑", "#9fb3c8", "right");
  };

  // ------------------------------------------------------------ DVH and profile
  function drawDVH(cv, st, S, ref) {
    const { g, W, H } = fitCanvas(cv);
    g.fillStyle = "#0b0f14"; g.fillRect(0, 0, W, H);
    const L = 44, R = W - 12, T = 26, B = H - 30, dmax = 16;
    g.strokeStyle = "#2a3441"; g.lineWidth = 1;
    for (let d = 0; d <= dmax; d += 2) { const x = L + (R - L) * d / dmax; g.beginPath(); g.moveTo(x, T); g.lineTo(x, B); g.stroke(); label(g, x, B + 14, String(d), "#8394a7", "center"); }
    for (let v = 0; v <= 100; v += 20) { const y = B - (B - T) * v / 100; g.beginPath(); g.moveTo(L, y); g.lineTo(R, y); g.stroke(); label(g, L - 6, y + 4, String(v), "#8394a7", "right"); }
    label(g, (L + R) / 2, H - 4, "Dose (Gy)", "#8394a7", "center"); label(g, 8, 16, "DVH", "#e8eef5", "left", "600 12px system-ui, sans-serif");
    const rx = ENG.state.plan.rx; g.strokeStyle = "rgba(255,225,77,0.6)"; g.setLineDash([4, 4]); g.beginPath();
    const xr = L + (R - L) * rx * 0.9 / dmax; g.moveTo(xr, T); g.lineTo(xr, B); g.stroke(); g.setLineDash([]);
    const curves = [["PTV", "#ff4d4d"], ["Lung_R", "#4fa3ff"], ["Lung_L", "#a07bff"], ["Lungs", "#4fd8ff"], ["Kidneys", "#ffd24d"], ["Body", "#7fdc7f"]];
    let ly = T + 6;
    if (ref) for (const [k, col] of curves) {
      const d = ref.dvh[k]; if (!d || !d.n || (S && S.showStruct[k] === false) || k === "Body") continue;
      g.strokeStyle = col; g.globalAlpha = 0.55; g.lineWidth = 1.2; g.setLineDash([2, 3]);
      g.beginPath(); d.curve.forEach(([dd, v], i) => { const x = L + (R - L) * dd / dmax, y = B - (B - T) * v / 100; i ? g.lineTo(x, y) : g.moveTo(x, y); }); g.stroke();
      g.setLineDash([]); g.globalAlpha = 1;
    }
    if (ref) { label(g, L + 6, B - 8, "dotted = reference plan", "#8394a7"); }
    for (const [k, col] of curves) {
      const d = st.dvh[k]; if (!d || !d.n || (S && S.showStruct[k] === false)) continue;
      g.strokeStyle = col; g.lineWidth = k === "Lungs" ? 1.2 : 2; if (k === "Lungs") g.setLineDash([5, 3]);
      g.beginPath(); d.curve.forEach(([dd, v], i) => { const x = L + (R - L) * dd / dmax, y = B - (B - T) * v / 100; i ? g.lineTo(x, y) : g.moveTo(x, y); }); g.stroke(); g.setLineDash([]);
      label(g, R - 6, ly + 4, `${k}  mean ${d.mean.toFixed(2)} Gy`, col, "right"); ly += 14;
    }
  }
  function profileData(S) {
    const pts = []; for (let z = 0.25; z < PH.LENGTH; z += 0.5) pts.push([z, ENG.doseAt(S.cross.x, S.cross.y, z)]);
    return pts;
  }
  function drawProfile(cv, S, ref) {
    const { g, W, H } = fitCanvas(cv);
    g.fillStyle = "#0b0f14"; g.fillRect(0, 0, W, H);
    const L = 44, R = W - 12, T = 26, B = H - 30, rx = ENG.state.plan.rx, dmin = 0.6 * rx, dmx = 1.2 * rx, zmax = PH.LENGTH;
    const Xz = z => L + (R - L) * z / zmax, Yd = d => B - (B - T) * (d - dmin) / (dmx - dmin);
    g.fillStyle = "rgba(76,217,100,0.08)"; g.fillRect(L, Yd(1.1 * rx), R - L, Yd(0.9 * rx) - Yd(1.1 * rx));
    const plan = ENG.state.plan;
    plan.isos.forEach((iso, i) => {
      g.fillStyle = ["rgba(88,166,255,0.07)", "rgba(255,159,67,0.07)", "rgba(61,220,151,0.07)"][i % 3];
      g.fillRect(Xz(iso.z + iso.lo), T, (iso.hi - iso.lo) * (R - L) / zmax, B - T);
    });
    g.strokeStyle = "#2a3441"; g.lineWidth = 1;
    for (let z = 0; z <= zmax; z += 10) { g.beginPath(); g.moveTo(Xz(z), T); g.lineTo(Xz(z), B); g.stroke(); label(g, Xz(z), B + 14, String(z), "#8394a7", "center"); }
    for (const f of [0.7, 0.8, 0.9, 1.0, 1.1]) { const y = Yd(f * rx); g.beginPath(); g.moveTo(L, y); g.lineTo(R, y); g.stroke(); label(g, L - 6, y + 4, `${Math.round(f * 100)}%`, "#8394a7", "right"); }
    const key = `${S.cross.x.toFixed(1)}_${S.cross.y.toFixed(1)}_${S.doseVersion}`;
    if (drawProfile._key !== key) { drawProfile._key = key; drawProfile._pts = profileData(S); }
    if (ref) {
      g.strokeStyle = "rgba(201,160,255,0.8)"; g.lineWidth = 1.4; g.setLineDash([3, 3]); g.beginPath(); let f2 = true;
      for (const [z, d] of ref) { if (d <= 0) { f2 = true; continue; } const x = Xz(z), y = Yd(Math.max(dmin, Math.min(dmx, d))); f2 ? g.moveTo(x, y) : g.lineTo(x, y); f2 = false; }
      g.stroke(); g.setLineDash([]); label(g, R - 6, T + 14, "dashed = reference plan", "#c9a0ff", "right");
    }
    g.strokeStyle = "#ffe14d"; g.lineWidth = 2; g.beginPath();
    let first = true;
    for (const [z, d] of drawProfile._pts) { if (d <= 0) { first = true; continue; } const x = Xz(z), y = Yd(Math.max(dmin, Math.min(dmx, d))); first ? g.moveTo(x, y) : g.lineTo(x, y); first = false; }
    g.stroke();
    label(g, 8, 16, `Longitudinal profile at x = ${S.cross.x.toFixed(1)}, y = ${S.cross.y.toFixed(1)} cm (junction check)`, "#e8eef5", "left", "600 12px system-ui, sans-serif");
    label(g, (L + R) / 2, H - 4, "Distance from vertex z (cm)", "#8394a7", "center");
  }

  return { SliceView, BEV, drawDVH, drawProfile, profileData, ISO_LEVELS, ISO_COL };
})();
