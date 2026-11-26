/* RT Planning Simulator — 2D views: axial / coronal / sagittal slices, beam's-eye view, DVH and dose profile. */
"use strict";
const V2 = (() => {
  const ISO_LEVELS = [
    { p: 110, c: "#ff2d55" }, { p: 105, c: "#ff8c1a" }, { p: 100, c: "#ffe14d" }, { p: 95, c: "#4cd964" },
    { p: 90, c: "#2ec5ff" }, { p: 80, c: "#3d7bff" }, { p: 50, c: "#b46bff" }, { p: 30, c: "#6c7a89" },
  ];
  const ISO_COL = ["#58a6ff", "#ff9f43", "#3ddc97", "#ff6b9a", "#c9a0ff", "#ffd75e", "#5ce1e6"];
  const DASH = [[], [6, 4], [2, 3], [10, 3, 2, 3], [1, 5]];

  function fitCanvas(cv) {
    const dpr = window.devicePixelRatio || 1, W = Math.max(10, cv.clientWidth), H = Math.max(10, cv.clientHeight);
    if (cv.width !== Math.round(W * dpr) || cv.height !== Math.round(H * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
    const g = cv.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { g, W, H };
  }
  // marching squares on vals[ny][nx] sampled at (x0 + i dx, y0 + j dy)
  const MS = { 1: [[3, 0]], 2: [[0, 1]], 3: [[3, 1]], 4: [[1, 2]], 5: [[3, 0], [1, 2]], 6: [[0, 2]], 7: [[3, 2]],
    8: [[2, 3]], 9: [[0, 2]], 10: [[0, 1], [2, 3]], 11: [[1, 2]], 12: [[1, 3]], 13: [[0, 1]], 14: [[0, 3]] };
  function contour(vals, nx, ny, x0, y0, dx, dy, lev) {
    const segs = [];
    for (let j = 0; j < ny - 1; j++) for (let i = 0; i < nx - 1; i++) {
      const a = vals[j * nx + i], b = vals[j * nx + i + 1], c = vals[(j + 1) * nx + i + 1], d = vals[(j + 1) * nx + i];
      let k = 0; if (a >= lev) k |= 1; if (b >= lev) k |= 2; if (c >= lev) k |= 4; if (d >= lev) k |= 8;
      if (k === 0 || k === 15) continue;
      const X = x0 + i * dx, Y = y0 + j * dy;
      const e = [[X + dx * (lev - a) / (b - a), Y], [X + dx, Y + dy * (lev - b) / (c - b)], [X + dx * (lev - d) / (c - d), Y + dy], [X, Y + dy * (lev - a) / (d - a)]];
      for (const [p, q] of MS[k]) segs.push([e[p][0], e[p][1], e[q][0], e[q][1]]);
    }
    return segs;
  }
  function washColor(f) {
    const st = [[0.3, [40, 40, 200]], [0.5, [60, 110, 255]], [0.8, [40, 200, 230]], [0.9, [60, 220, 120]], [0.95, [190, 235, 60]],
      [1.0, [255, 220, 40]], [1.05, [255, 140, 20]], [1.12, [240, 30, 40]]];
    if (f < st[0][0]) return null;
    for (let i = 1; i < st.length; i++) if (f <= st[i][0]) {
      const t = (f - st[i - 1][0]) / (st[i][0] - st[i - 1][0]), a = st[i - 1][1], b = st[i][1];
      return [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), a[2] + t * (b[2] - a[2])];
    }
    return st[st.length - 1][1];
  }
  // diverging colour for dose differences (f = difference / prescription), blue = colder, red = hotter
  function diffColor(f) {
    const a = Math.min(1, Math.abs(f) / 0.1); if (a < 0.08) return null;
    return f > 0 ? [255, 255 * (1 - a) * 0.6, 60 * (1 - a)] : [60 * (1 - a), 140 * (1 - a) + 60, 255];
  }
  function label(g, x, y, t, col = "#cfd8e3", align = "left", font = "11px system-ui, sans-serif") {
    g.font = font; g.textAlign = align; g.fillStyle = "rgba(0,0,0,0.6)"; g.fillText(t, x + 1, y + 1); g.fillStyle = col; g.fillText(t, x, y);
  }
  // dose of the selected source at a point
  function doseOf(S, x, y, z) {
    const src = S.doseSrc || { kind: "plan" }, snap = id => S.snapshots.find(s => s.id === id);
    if (src.kind === "plan") return ENG.doseAt(x, y, z);
    const A = snap(src.a); if (!A) return ENG.doseAt(x, y, z);
    const a = ENG.sampleGrid(A.grid, A.dose, x, y, z);
    if (src.kind === "snap") return a;
    if (src.kind === "diff") return ENG.doseAt(x, y, z) - a;
    if (src.kind === "sum") { const B = snap(src.b); return a + (B ? ENG.sampleGrid(B.grid, B.dose, x, y, z) : 0); }
    return 0;
  }
  // isocentre groups (beams sharing an isocentre and orientation), sorted along the body
  function isoGroups(plan) {
    const G = [];
    plan.beams.forEach((b, i) => {
      if (b.off) return;
      let g = G.find(q => Math.abs(q.iso.x - b.iso.x) < 0.01 && Math.abs(q.iso.y - b.iso.y) < 0.01 && Math.abs(q.iso.z - b.iso.z) < 0.01 && q.orient === b.orient);
      if (!g) { g = { iso: b.iso, orient: b.orient || "HFS", beams: [], zlo: 1e9, zhi: -1e9, half: 0 }; G.push(g); }
      g.beams.push(i);
      const f = b.orient === "FFS" ? -1 : 1, cr = (b.coll || 0) * Math.PI / 180, k = (b.sad || 100) / 100;
      for (const X of [b.X1, b.X2]) for (const Y of [b.Y1, b.Y2]) {
        const u = X * Math.cos(cr) - Y * Math.sin(cr), w = X * Math.sin(cr) + Y * Math.cos(cr);
        const z = b.iso.z + f * w; g.zlo = Math.min(g.zlo, z); g.zhi = Math.max(g.zhi, z); g.half = Math.max(g.half, Math.abs(u));
      }
      void k;
    });
    G.sort((a, b) => a.iso.z - b.iso.z);
    G.forEach((g, i) => g.label = plan.beams[g.beams[0]].name.replace(/\d+$/, "").replace(/[-_ ]?(AP|PA)$/i, "") || `Iso ${i + 1}`);
    return G;
  }

  // ------------------------------------------------------------ slice views
  function SliceView(cv, kind) { this.cv = cv; this.kind = kind; this.cache = {}; this.zoom = 1; this.pan = [0, 0]; }
  SliceView.prototype.extent = function () {
    const sg = CASE.sg, x0 = sg.x0, x1 = sg.x0 + sg.nx * sg.h, y0 = sg.y0, y1 = sg.y0 + sg.ny * sg.h, z0 = sg.z0, z1 = sg.z0 + sg.nz * sg.h;
    if (this.kind === "axial") return { u0: x0 - 1, u1: x1 + 1, v0: y0 - 1, v1: y1 + 1 };
    if (this.kind === "coronal") return { u0: x0 - 1, u1: x1 + 1, v0: z0 - 2, v1: z1 + 2 };
    return { u0: y0 - 1, u1: y1 + 1, v0: z0 - 2, v1: z1 + 2 };
  };
  SliceView.prototype.world = function (u, v, X) {
    if (this.kind === "axial") return [u, v, X.z];
    if (this.kind === "coronal") return [u, X.y, v];
    return [X.x, u, v];
  };
  SliceView.prototype.map = function (W, H) {
    const e = this.extent(), s = Math.min(W / (e.u1 - e.u0), H / (e.v1 - e.v0)) * this.zoom;
    const ox = W / 2 - s * (e.u0 + e.u1) / 2 + this.pan[0], oy = H / 2 - s * (e.v0 + e.v1) / 2 + this.pan[1];
    return { s, ox, oy, X: u => ox + u * s, Y: v => oy + v * s, U: px => (px - ox) / s, V: py => (py - oy) / s };
  };
  SliceView.prototype.sliceKey = function (X) { return (this.kind === "axial" ? X.z : this.kind === "coronal" ? X.y : X.x).toFixed(2); };
  SliceView.prototype.ctImage = function (X, win) {
    const key = CASE.ph.id + this.sliceKey(X) + win.c + "_" + win.w;
    if (this.cache.ctKey === key) return this.cache.ct;
    const e = this.extent(), span = Math.max(e.u1 - e.u0, e.v1 - e.v0), h = this.kind === "axial" ? Math.max(0.1, span / 300) : Math.max(0.2, span / 520);
    const nx = Math.round((e.u1 - e.u0) / h), ny = Math.round((e.v1 - e.v0) / h);
    const cv = document.createElement("canvas"); cv.width = nx; cv.height = ny;
    const g = cv.getContext("2d"), img = g.createImageData(nx, ny), lo = win.c - win.w / 2, ph = CASE.ph, ax = this.kind === "axial";
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      const [x, y, z] = this.world(e.u0 + (i + 0.5) * h, e.v0 + (j + 0.5) * h, X);
      let hu = z < ph.z0 || z > ph.z1 ? -1000 : ph.hu(x, y, z, ax);
      const v = Math.max(0, Math.min(255, (hu - lo) / win.w * 255)), o = 4 * (j * nx + i);
      img.data[o] = v; img.data[o + 1] = v; img.data[o + 2] = v; img.data[o + 3] = 255;
    }
    g.putImageData(img, 0, 0);
    this.cache.ctKey = key; this.cache.ct = { cv, e };
    return this.cache.ct;
  };
  SliceView.prototype.structSegs = function (X) {
    const key = this.sliceKey(X) + "_" + CASE.version;
    if (this.cache.stKey === key) return this.cache.st;
    const out = {};
    for (const s of CASE.structs) {
      const m = CASE.maskSlice(s.id, this.kind, X);
      out[s.id] = contour(m.vals, m.nx, m.ny, m.x0, m.y0, m.h, m.h, 0.5);
    }
    this.cache.stKey = key; this.cache.st = out;
    return out;
  };
  SliceView.prototype.doseGrid = function (X, S) {
    const src = S.doseSrc || { kind: "plan" };
    const key = this.sliceKey(X) + "_" + S.doseVersion + "_" + JSON.stringify(src);
    if (this.cache.dKey === key) return this.cache.d;
    const e = this.extent(), h = this.kind === "axial" ? Math.max(0.25, (e.u1 - e.u0) / 110) : Math.max(0.35, (e.v1 - e.v0) / 240);
    const nx = Math.round((e.u1 - e.u0) / h) + 1, ny = Math.round((e.v1 - e.v0) / h) + 1, vals = new Float32Array(nx * ny);
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      const [x, y, z] = this.world(e.u0 + i * h, e.v0 + j * h, X);
      vals[j * nx + i] = CASE.bitsAt(x, y, z) & 1 ? doseOf(S, x, y, z) : 0;
    }
    this.cache.dKey = key; this.cache.d = { vals, nx, ny, h, e };
    return this.cache.d;
  };
  SliceView.prototype.draw = function (S) {
    const { g, W, H } = fitCanvas(this.cv), m = this.map(W, H), X = S.cross, plan = ENG.state.plan, rx = plan.rx;
    g.fillStyle = "#000"; g.fillRect(0, 0, W, H);
    const ct = this.ctImage(X, S.window);
    g.imageSmoothingEnabled = true;
    g.drawImage(ct.cv, m.X(ct.e.u0), m.Y(ct.e.v0), (ct.e.u1 - ct.e.u0) * m.s, (ct.e.v1 - ct.e.v0) * m.s);
    const src = S.doseSrc || { kind: "plan" };
    if (S.doseMode !== "none") {
      const d = this.doseGrid(X, S);
      if (S.doseMode === "wash" || src.kind === "diff") {
        const cv = document.createElement("canvas"); cv.width = d.nx; cv.height = d.ny;
        const cg = cv.getContext("2d"), img = cg.createImageData(d.nx, d.ny);
        for (let q = 0; q < d.vals.length; q++) {
          const c = src.kind === "diff" ? diffColor(d.vals[q] / rx) : washColor(d.vals[q] / rx);
          if (c) { img.data[4 * q] = c[0]; img.data[4 * q + 1] = c[1]; img.data[4 * q + 2] = c[2]; img.data[4 * q + 3] = src.kind === "diff" ? 150 : 120; }
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
    const st = this.structSegs(X);
    for (const s of CASE.structs) {
      if (!s.visible) continue;
      g.strokeStyle = s.color; g.lineWidth = S.editStruct === s.id ? 2.4 : 1.4; g.beginPath();
      for (const q of st[s.id]) { g.moveTo(m.X(q[0]), m.Y(q[1])); g.lineTo(m.X(q[2]), m.Y(q[3])); }
      g.stroke();
    }
    if (S.showBeams) this.drawBeams(g, m, S);
    // crosshair
    g.strokeStyle = "rgba(255,230,90,0.55)"; g.lineWidth = 1; g.setLineDash([4, 4]); g.beginPath();
    const [cu, cv2] = this.kind === "axial" ? [X.x, X.y] : this.kind === "coronal" ? [X.x, X.z] : [X.y, X.z];
    g.moveTo(m.X(cu), 0); g.lineTo(m.X(cu), H); g.moveTo(0, m.Y(cv2)); g.lineTo(W, m.Y(cv2)); g.stroke(); g.setLineDash([]);
    // points of interest (point doses)
    for (const p of S.points || []) {
      const [pu, pv, pw] = this.kind === "axial" ? [p.x, p.y, p.z - X.z] : this.kind === "coronal" ? [p.x, p.z, p.y - X.y] : [p.y, p.z, p.x - X.x];
      if (Math.abs(pw) > 1) continue;
      g.strokeStyle = "#fff"; g.lineWidth = 1.5; g.beginPath(); g.arc(m.X(pu), m.Y(pv), 5, 0, 7); g.stroke();
      label(g, m.X(pu) + 7, m.Y(pv) - 6, p.name, "#fff");
    }
    if (S.brush && S.brush.view === this.kind && S.brush.r) {
      g.strokeStyle = S.brush.erase ? "#ff6b6b" : "#7CFC00"; g.lineWidth = 1; g.beginPath(); g.arc(S.brush.px, S.brush.py, S.brush.r * m.s, 0, 7); g.stroke();
    }
    const title = { axial: `Axial  z = ${X.z.toFixed(1)} cm`, coronal: `Coronal  y = ${X.y.toFixed(1)} cm`, sagittal: `Sagittal  x = ${X.x.toFixed(1)} cm` }[this.kind];
    label(g, 8, 16, title, "#e8eef5", "left", "600 12px system-ui, sans-serif");
    const dv = doseOf(S, X.x, X.y, X.z), srcName = src.kind === "plan" ? "" : src.kind === "diff" ? " (difference)" : src.kind === "sum" ? " (plan sum)" : " (snapshot)";
    label(g, 8, 32, `Dose${srcName}: ${dv.toFixed(2)} Gy (${(100 * dv / rx).toFixed(1)}%)  ρ ${CASE.rhoAt(X.x, X.y, X.z).toFixed(2)}`, "#9fb3c8");
    const o = { axial: ["R", "L", "A", "P"], coronal: ["R", "L", "H", "F"], sagittal: ["A", "P", "H", "F"] }[this.kind];
    label(g, 6, H / 2, o[0], "#ffd75e"); label(g, W - 14, H / 2, o[1], "#ffd75e");
    label(g, W / 2, 14, o[2], "#ffd75e", "center"); label(g, W / 2, H - 6, o[3], "#ffd75e", "center");
    if (src.kind === "diff") label(g, W - 8, 32, "red = hotter, blue = colder (±10 % of Rx)", "#ffb3b3", "right");
    g.strokeStyle = "#cfd8e3"; g.lineWidth = 2; g.beginPath(); g.moveTo(W - 14 - 10 * m.s, H - 14); g.lineTo(W - 14, H - 14); g.stroke();
    label(g, W - 14 - 5 * m.s, H - 18, "10 cm", "#cfd8e3", "center");
    this._m = m;
  };
  SliceView.prototype.drawBeams = function (g, m, S) {
    const plan = ENG.state.plan, cps = ENG.state.cps, cur = S.cp;
    if (this.kind === "axial") {
      const z = S.cross.z;
      // beams crossing this slice: arc tracks as faint spokes, static fields as their edges
      plan.beams.forEach((b, bi) => {
        if (b.off) return;
        const mine = cps.filter(c => c.beam === bi && z >= c.zlo && z <= c.zhi);
        if (!mine.length) return;
        const isCur = cur && cur.beam === bi;
        for (const c of mine) {
          const ur = uRange(c, z); if (!ur) continue;
          const col = isCur ? (c === cur ? "rgba(255,160,60,0.9)" : "rgba(255,170,60,0.16)") : "rgba(150,170,200,0.12)";
          if (b.type === "arc" && c !== cur) { g.strokeStyle = col; g.lineWidth = 1; g.beginPath(); g.moveTo(m.X(c.ix + (c.sx - c.ix) * 0.35), m.Y(c.iy + (c.sy - c.iy) * 0.35)); g.lineTo(m.X(c.ix), m.Y(c.iy)); g.stroke(); continue; }
          fan(g, m, c, ur, c === cur ? "rgba(255,140,30,0.06)" : "rgba(120,160,255,0.04)", c === cur ? "rgba(255,160,60,0.9)" : "rgba(130,170,255,0.55)");
        }
      });
      if (cur) {
        label(g, m.X(cur.ix + (cur.sx - cur.ix) * 0.17), m.Y(cur.iy + (cur.sy - cur.iy) * 0.17), `G ${cur.theta.toFixed(0)}°`, "#ffb35c", "center", "600 11px system-ui, sans-serif");
        g.fillStyle = "#ff5a4f"; g.beginPath(); g.arc(m.X(cur.ix), m.Y(cur.iy), 3, 0, 7); g.fill();
      }
      return;
    }
    // coronal / sagittal: field extents of every isocentre group, overlaps and gaps
    const G = isoGroups(plan), sag = this.kind === "sagittal";
    G.forEach((q, i) => {
      const col = ISO_COL[i % ISO_COL.length], isCur = cur && q.beams.includes(cur.beam), c = sag ? q.iso.y : q.iso.x;
      g.strokeStyle = col; g.lineWidth = isCur ? 2.2 : 1.2; g.setLineDash(isCur ? [] : [6, 4]);
      g.strokeRect(m.X(c - q.half + i * 0.3), m.Y(q.zlo), m.s * (2 * q.half - i * 0.6), m.s * (q.zhi - q.zlo));
      g.setLineDash([]);
      g.fillStyle = col; g.beginPath(); g.arc(m.X(c), m.Y(q.iso.z), 3.5, 0, 7); g.fill();
      label(g, m.X(c + q.half) - 4, m.Y(q.iso.z) - 4, `${q.label} ${q.orient}`, col, "right", "600 11px system-ui, sans-serif");
    });
    if (G.length > 1 && CASE.ph.kind === "tbi") for (let i = 0; i < G.length - 1; i++) {
      const a = G[i], b = G[i + 1], z1 = b.zlo, z2 = a.zhi, x0 = sag ? CASE.sg.y0 : CASE.sg.x0, w = (sag ? CASE.sg.ny : CASE.sg.nx) * CASE.sg.h;
      if (z2 > z1) { g.fillStyle = "rgba(255,255,255,0.10)"; g.fillRect(m.X(x0), m.Y(z1), w * m.s, (z2 - z1) * m.s); label(g, m.X(x0) + 4, m.Y((z1 + z2) / 2) + 4, `overlap ${(z2 - z1).toFixed(1)} cm`, "#e8eef5"); }
      else { g.fillStyle = "rgba(255,60,60,0.25)"; g.fillRect(m.X(x0), m.Y(z2), w * m.s, (z1 - z2) * m.s); label(g, m.X(x0) + 4, m.Y((z1 + z2) / 2) + 4, `GAP ${(z1 - z2).toFixed(1)} cm`, "#ff6b6b"); }
    }
  };
  // lateral extent (u at the isocentre plane) of a control point's jaws at slice z
  function uRange(cp, z) {
    const w = (z - cp.iz) * cp.flip, us = [];
    const corners = [[cp.X1, cp.Y1], [cp.X2, cp.Y1], [cp.X2, cp.Y2], [cp.X1, cp.Y2]].map(([X, Y]) => [X * cp.cc - Y * cp.cs, X * cp.cs + Y * cp.cc]);
    for (let i = 0; i < 4; i++) {
      const [u1, w1] = corners[i], [u2, w2] = corners[(i + 1) % 4];
      if ((w1 - w) * (w2 - w) <= 0 && w1 !== w2) us.push(u1 + (u2 - u1) * (w - w1) / (w2 - w1));
    }
    if (us.length < 2) return null;
    return [Math.min(...us) * cp.flip, Math.max(...us) * cp.flip].sort((a, b) => a - b);
  }
  function fan(g, m, cp, ur, fill, stroke) {
    const ext = cp.sad + 45, dirx = -cp.s, diry = cp.c, ux = cp.c, uy = cp.s;
    const end = u => [cp.sx + ext * dirx + u * (ext / cp.sad) * ux, cp.sy + ext * diry + u * (ext / cp.sad) * uy];
    const e1 = end(ur[0]), e2 = end(ur[1]);
    g.fillStyle = fill; g.beginPath(); g.moveTo(m.X(cp.sx), m.Y(cp.sy)); g.lineTo(m.X(e1[0]), m.Y(e1[1])); g.lineTo(m.X(e2[0]), m.Y(e2[1])); g.closePath(); g.fill();
    g.strokeStyle = stroke; g.lineWidth = 1.2; g.beginPath();
    g.moveTo(m.X(cp.sx), m.Y(cp.sy)); g.lineTo(m.X(e1[0]), m.Y(e1[1])); g.moveTo(m.X(cp.sx), m.Y(cp.sy)); g.lineTo(m.X(e2[0]), m.Y(e2[1])); g.stroke();
    g.setLineDash([6, 4]); g.beginPath(); const ce = end(0); g.moveTo(m.X(cp.sx), m.Y(cp.sy)); g.lineTo(m.X(ce[0]), m.Y(ce[1])); g.stroke(); g.setLineDash([]);
  }

  // ------------------------------------------------------------ beam's-eye view (collimator frame)
  function BEV(cv) { this.cv = cv; this.cache = {}; }
  BEV.prototype.silhouettes = function (cp, S) {
    const key = ENG.state.cps.indexOf(cp) + "_" + CASE.version + "_" + ENG.state.version;
    if (this.cache.key === key) return this.cache.sil;
    const grid = ENG.state.grid, pad = 6, X0 = cp.X1 - pad, Y0 = cp.Y1 - pad, h = Math.max(0.5, (cp.X2 - cp.X1 + 2 * pad) / 140);
    const nx = Math.ceil((cp.X2 - cp.X1 + 2 * pad) / h) + 1, ny = Math.ceil((cp.Y2 - cp.Y1 + 2 * pad) / h) + 1, out = {}, o = new Float64Array(6);
    for (const s of CASE.structs) {
      if (!s.visible) continue;
      const occ = new Float32Array(nx * ny), vox = ENG.voxOf(grid, s.bit, true);
      for (let q = 0; q < vox.length; q++) {
        const v = vox[q];
        if (!ENG.project(cp, grid.x[v], grid.y[v], grid.z[v], o)) continue;
        const r = grid.h * o[3] * 0.6, i0 = Math.floor((o[0] - r - X0) / h), i1 = Math.floor((o[0] + r - X0) / h), j0 = Math.floor((o[1] - r - Y0) / h), j1 = Math.floor((o[1] + r - Y0) / h);
        for (let j = Math.max(0, j0); j <= Math.min(ny - 1, j1); j++) for (let i = Math.max(0, i0); i <= Math.min(nx - 1, i1); i++) occ[j * nx + i] = 1;
      }
      out[s.id] = contour(occ, nx, ny, X0, Y0, h, h, 0.5);
    }
    this.cache.key = key; this.cache.sil = out;
    return out;
  };
  BEV.prototype.draw = function (S) {
    const { g, W, H } = fitCanvas(this.cv), cp = S.cp;
    g.fillStyle = "#05070a"; g.fillRect(0, 0, W, H);
    if (!cp) { label(g, 10, 20, "No beams", "#9fb3c8"); return; }
    const plan = ENG.state.plan, b = plan.beams[cp.beam], pad = 3;
    const xr0 = cp.X1 - pad, xr1 = cp.X2 + pad, yr0 = cp.Y1 - pad, yr1 = cp.Y2 + pad;
    const s = Math.min((W - 20) / (xr1 - xr0), (H - 70) / (yr1 - yr0)), ox = W / 2 - s * (xr0 + xr1) / 2, oy = 34 + (H - 70) / 2 - s * (yr0 + yr1) / 2 + 18;
    const X = u => ox + u * s, Y = w => oy + w * s;     // +Y downwards (towards the feet for HFS, collimator 0°)
    // fluence (or deliverable fluence after Stage 2) as a smooth image
    const F = cp.Fs; let mx = 0; for (const f of F) mx = Math.max(mx, f);
    const im = document.createElement("canvas"); im.width = cp.nX; im.height = cp.nY;
    const ig = im.getContext("2d"), id = ig.createImageData(cp.nX, cp.nY);
    for (let j = 0; j < cp.nX; j++) for (let i = 0; i < cp.nY; i++) {
      const f = F[j * cp.nY + i] / (mx || 1), o = 4 * (i * cp.nX + j);
      id.data[o] = 255 * Math.min(1, f * 1.4); id.data[o + 1] = 200 * f; id.data[o + 2] = 60 + 80 * f; id.data[o + 3] = 40 + 170 * f;
    }
    ig.putImageData(id, 0, 0);
    g.imageSmoothingEnabled = true;
    g.drawImage(im, X(cp.X1), Y(cp.Y1), (cp.X2 - cp.X1) * s, (cp.Y2 - cp.Y1) * s);
    // projected structures
    const sil = this.silhouettes(cp, S);
    for (const st of CASE.structs) {
      if (!st.visible || !sil[st.id]) continue;
      g.strokeStyle = st.color; g.lineWidth = st.role === "target" ? 1.8 : 1.3; g.beginPath();
      for (const q of sil[st.id]) { g.moveTo(X(q[0]), Y(q[1])); g.lineTo(X(q[2]), Y(q[3])); }
      g.stroke();
    }
    // blocks (conventional TBI)
    if (cp.block) {
      g.fillStyle = "rgba(170,180,195,0.55)";
      for (let j = 0; j < cp.nX; j++) for (let i = 0; i < cp.nY; i++) if (cp.block[j * cp.nY + i]) g.fillRect(X(cp.X1 + j * cp.binX), Y(cp.Y1 + i * cp.binY), cp.binX * s + 0.5, cp.binY * s + 0.5);
    }
    // MLC
    const lv = ENG.leaves(cp, S.segIndex || 0);
    if (S.showMLC && b.mlc !== "blocks") {
      g.lineWidth = 0.5;
      for (let i = 0; i < cp.nY; i++) {
        const y0 = cp.Y1 + i * cp.binY, y1 = y0 + cp.binY;
        g.fillStyle = lv.preview ? "rgba(120,135,155,0.55)" : "rgba(130,145,165,0.85)"; g.strokeStyle = "rgba(15,20,26,0.9)";
        const L = lv.l[i], R = lv.r[i];
        g.fillRect(X(xr0), Y(y0), (L - xr0) * s, cp.binY * s); g.strokeRect(X(xr0), Y(y0), (L - xr0) * s, cp.binY * s);
        g.fillRect(X(R), Y(y0), (xr1 - R) * s, cp.binY * s); g.strokeRect(X(R), Y(y0), (xr1 - R) * s, cp.binY * s);
      }
    }
    // jaws
    g.strokeStyle = "#ffd75e"; g.lineWidth = 2; g.strokeRect(X(cp.X1), Y(cp.Y1), (cp.X2 - cp.X1) * s, (cp.Y2 - cp.Y1) * s);
    // wedge symbol
    if (b.wedge && b.wedge.angle) {
      const d = b.wedge.dir || "+X", cx = X((cp.X1 + cp.X2) / 2), cy = Y(cp.Y1) - 6;
      g.fillStyle = "rgba(255,215,94,0.8)"; g.beginPath();
      const L2 = 26, sgn = d[0] === "+" ? 1 : -1;
      if (d[1] === "X") { g.moveTo(cx - L2 * sgn, cy); g.lineTo(cx + L2 * sgn, cy); g.lineTo(cx + L2 * sgn, cy - 9); }
      else { g.moveTo(cx, cy - 4); g.lineTo(cx + 9, cy - 4); g.lineTo(cx, cy - 4 - 14 * sgn); }
      g.closePath(); g.fill(); label(g, cx + 32, cy, `wedge ${b.wedge.angle}° thick end ${d}`, "#ffd75e");
    }
    // graticule
    g.strokeStyle = "rgba(255,255,255,0.35)"; g.lineWidth = 1; g.beginPath();
    g.moveTo(X(xr0), Y(0)); g.lineTo(X(xr1), Y(0)); g.moveTo(X(0), Y(yr0)); g.lineTo(X(0), Y(yr1)); g.stroke();
    const tick = (cp.X2 - cp.X1) > 60 ? 10 : 5;
    for (let t = Math.ceil(xr0 / tick) * tick; t <= xr1; t += tick) { g.beginPath(); g.moveTo(X(t), Y(0) - 3); g.lineTo(X(t), Y(0) + 3); g.stroke(); }
    const segTxt = lv.preview ? "aperture preview (Stage 1 fluence)" : `segment ${lv.idx + 1}/${lv.n}`;
    label(g, 8, 16, `BEV · ${b.name} · ${b.type === "arc" ? `arc ${b.dir} ${b.start}→${b.stop}°` : "static field"} · ${b.energy} · ${b.orient}${b.sad > 100 ? ` · SAD ${b.sad} cm` : ""}`, "#e8eef5", "left", "600 12px system-ui, sans-serif");
    label(g, 8, 32, `Gantry ${cp.theta.toFixed(1)}° · Coll ${b.coll || 0}° · Couch 0° · ${segTxt}`, "#ffb35c");
    label(g, 8, 48, `Jaws X ${cp.X1.toFixed(1)} / ${cp.X2.toFixed(1)} · Y ${cp.Y1.toFixed(1)} / ${cp.Y2.toFixed(1)} cm (at isocentre) · ${b.mlc}`, "#9fb3c8");
    label(g, W - 8, H - 8, "collimator frame: X →, Y ↓", "#9fb3c8", "right");
  };

  // ------------------------------------------------------------ DVH and profile
  function drawDVH(cv, st, S, snaps) {
    const { g, W, H } = fitCanvas(cv), rx = st.rx;
    g.fillStyle = "#0b0f14"; g.fillRect(0, 0, W, H);
    const L = 44, R = W - 12, T = 26, B = H - 30, dmax = Math.ceil(1.25 * rx / 5) * 5 || 15, step = dmax > 60 ? 10 : dmax > 30 ? 5 : 2;
    g.strokeStyle = "#2a3441"; g.lineWidth = 1;
    for (let d = 0; d <= dmax + 1e-6; d += step) { const x = L + (R - L) * d / dmax; g.beginPath(); g.moveTo(x, T); g.lineTo(x, B); g.stroke(); label(g, x, B + 14, String(d), "#8394a7", "center"); }
    for (let v = 0; v <= 100; v += 20) { const y = B - (B - T) * v / 100; g.beginPath(); g.moveTo(L, y); g.lineTo(R, y); g.stroke(); label(g, L - 6, y + 4, String(v), "#8394a7", "right"); }
    label(g, (L + R) / 2, H - 4, "Dose (Gy)", "#8394a7", "center"); label(g, 8, 16, "DVH (volume %)", "#e8eef5", "left", "600 12px system-ui, sans-serif");
    g.strokeStyle = "rgba(255,225,77,0.6)"; g.setLineDash([4, 4]); g.beginPath(); const xr = L + (R - L) * rx / dmax; g.moveTo(xr, T); g.lineTo(xr, B); g.stroke(); g.setLineDash([]);
    const names = CASE.names().filter(n => { const s = CASE.find(n); return s ? s.visible && s.role !== "body" : S.showGroups !== false; });
    const curve = (d, col, w, dash, alpha) => {
      g.strokeStyle = col; g.lineWidth = w; g.globalAlpha = alpha; g.setLineDash(dash); g.beginPath();
      d.curve.forEach(([dd, v], i) => { const x = L + (R - L) * Math.min(dd, dmax) / dmax, y = B - (B - T) * v / 100; i ? g.lineTo(x, y) : g.moveTo(x, y); });
      g.stroke(); g.setLineDash([]); g.globalAlpha = 1;
    };
    (snaps || []).forEach((sn, k) => { for (const n of names) { const d = sn.stats.dvh[n]; if (d && d.n) curve(d, CASE.colorOf(n), 1.2, DASH[1 + (k % 4)], 0.75); } });
    const shown = names.filter(n => st.dvh[n] && st.dvh[n].n);
    for (const n of shown) curve(st.dvh[n], CASE.colorOf(n), 2, [], 1);
    // legend on a dark box so it stays readable over the curves
    g.font = "11px system-ui, sans-serif";
    const lw = Math.max(60, ...shown.map(n => g.measureText(`${n}  mean ${st.dvh[n].mean.toFixed(2)} Gy`).width)) + 12;
    g.fillStyle = "rgba(11,15,20,0.82)"; g.fillRect(R - lw - 2, T + 2, lw, 14 * shown.length + 6);
    let ly = T + 6;
    for (const n of shown) { label(g, R - 6, ly + 8, `${n}  mean ${st.dvh[n].mean.toFixed(2)} Gy`, CASE.colorOf(n), "right"); ly += 14; }
    (snaps || []).forEach((sn, k) => {
      const y = B - 10 - 14 * k; g.strokeStyle = "#cfd8e3"; g.setLineDash(DASH[1 + (k % 4)]); g.beginPath(); g.moveTo(L + 8, y - 4); g.lineTo(L + 38, y - 4); g.stroke(); g.setLineDash([]);
      label(g, L + 44, y, sn.name, "#cfd8e3");
    });
  }
  function profileData(S, axis) {
    const sg = CASE.sg, pts = [], X = S.cross;
    const [a0, a1] = axis === "z" ? [sg.z0, sg.z0 + sg.nz * sg.h] : axis === "x" ? [sg.x0, sg.x0 + sg.nx * sg.h] : [sg.y0, sg.y0 + sg.ny * sg.h];
    const at = t => axis === "z" ? [X.x, X.y, t] : axis === "x" ? [t, X.y, X.z] : [X.x, t, X.z];
    const step = (a1 - a0) / 260;
    for (let t = a0 + step / 2; t < a1; t += step) {
      const [x, y, z] = at(t);
      // skip points within 0.6 cm of the skin (build-up region) to keep the junction plot readable
      const [xa, ya, za] = at(t - 0.6), [xb, yb, zb] = at(t + 0.6);
      const inside = CASE.bitsAt(x, y, z) & 1 && CASE.bitsAt(xa, ya, za) & 1 && CASE.bitsAt(xb, yb, zb) & 1;
      pts.push([t, inside ? doseOf(S, x, y, z) : null]);
    }
    return pts;
  }
  function drawProfile(cv, S, refs) {
    const { g, W, H } = fitCanvas(cv), rx = ENG.state.plan.rx, axis = S.profAxis || (CASE.ph.kind === "tbi" ? "z" : "x");
    g.fillStyle = "#0b0f14"; g.fillRect(0, 0, W, H);
    const pts = profileData(S, axis), L = 44, R = W - 12, T = 26, B = H - 30, a0 = pts[0][0], a1 = pts[pts.length - 1][0];
    const tbi = CASE.ph.kind === "tbi", dmin = tbi ? 0.6 * rx : 0, dmx = tbi ? 1.2 * rx : 1.15 * rx;
    const Xa = t => L + (R - L) * (t - a0) / (a1 - a0), Yd = d => B - (B - T) * (d - dmin) / (dmx - dmin);
    g.fillStyle = "rgba(76,217,100,0.08)"; g.fillRect(L, Yd(1.1 * rx), R - L, Yd(0.9 * rx) - Yd(1.1 * rx));
    if (axis === "z") isoGroups(ENG.state.plan).forEach((q, i) => { g.fillStyle = ISO_COL[i % ISO_COL.length] + "14"; g.fillRect(Xa(q.zlo), T, (q.zhi - q.zlo) * (R - L) / (a1 - a0), B - T); });
    g.strokeStyle = "#2a3441"; g.lineWidth = 1;
    const st = (a1 - a0) > 100 ? 20 : (a1 - a0) > 50 ? 10 : 5;
    for (let t = Math.ceil(a0 / st) * st; t <= a1; t += st) { g.beginPath(); g.moveTo(Xa(t), T); g.lineTo(Xa(t), B); g.stroke(); label(g, Xa(t), B + 14, String(t), "#8394a7", "center"); }
    for (const f of tbi ? [0.7, 0.8, 0.9, 1.0, 1.1] : [0, 0.25, 0.5, 0.75, 1.0, 1.1]) { const y = Yd(f * rx); g.beginPath(); g.moveTo(L, y); g.lineTo(R, y); g.stroke(); label(g, L - 6, y + 4, `${Math.round(f * 100)}%`, "#8394a7", "right"); }
    const line = (P, col, w, dash) => {
      g.strokeStyle = col; g.lineWidth = w; g.setLineDash(dash); g.beginPath(); let first = true;
      for (const [t, d] of P) { if (d === null) { first = true; continue; } const x = Xa(t), y = Yd(Math.max(dmin, Math.min(dmx, d))); first ? g.moveTo(x, y) : g.lineTo(x, y); first = false; }
      g.stroke(); g.setLineDash([]);
    };
    (refs || []).forEach((r, k) => { if (r.axis === axis && r.pts) line(r.pts, "rgba(201,160,255,0.85)", 1.4, DASH[1 + (k % 4)]); });
    line(pts, "#ffe14d", 2, []);
    const nm = { z: "head–foot (z)", x: "right–left (x)", y: "anterior–posterior (y)" }[axis];
    label(g, 8, 16, `Dose profile ${nm} through the crosshair${tbi && axis === "z" ? " (junction check)" : ""}`, "#e8eef5", "left", "600 12px system-ui, sans-serif");
    label(g, (L + R) / 2, H - 4, `${axis} (cm)`, "#8394a7", "center");
    return pts;
  }

  return { SliceView, BEV, drawDVH, drawProfile, profileData, doseOf, isoGroups, ISO_LEVELS, ISO_COL, contour, DASH };
})();
