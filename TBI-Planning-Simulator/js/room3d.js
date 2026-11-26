/* RT Planning Simulator — 3D treatment-room view (generic linac, couch, phantom, beams, arc tracks).
 * Room frame: X = machine left-right, Y = up, Z = along the couch (gantry at negative Z); isocentre at the origin. */
"use strict";
const ROOM = (() => {
  const { M } = GLX;
  let ctx = null, canvas = null, meshes = {}, patient = null;
  const cam = { yaw: 0.95, pitch: 0.42, dist: 330, tx: 0, ty: -18, tz: 30 };
  const ISO_H = 127;
  const opts = { transparent: true, showTracks: true, showBeam: true, showLasers: true, showRoom: true, showAll: true };

  function buildStatic() {
    const U = m => GLX.upload(ctx, m);
    meshes.floor = U(GLX.box(900, 2, 900)); meshes.wall = U(GLX.box(900, 320, 2));
    meshes.stand = U(GLX.box(190, 250, 70)); meshes.drum = U(GLX.cyl(92, 10, 64)); meshes.drumRing = U(GLX.cyl(70, 11, 64));
    meshes.arm = U(GLX.box(56, 30, 120)); meshes.head = U(GLX.box(64, 40, 62)); meshes.headNose = U(GLX.cyl(30, 22, 48, 24));
    meshes.panel = U(GLX.box(44, 3, 44)); meshes.panelArm = U(GLX.box(8, 8, 95));
    meshes.pedestal = U(GLX.box(46, 90, 60)); meshes.couchBase = U(GLX.box(70, 12, 120)); meshes.couchTop = U(GLX.box(53, 5, 215));
    meshes.isoMark = U(GLX.box(2.4, 2.4, 2.4)); meshes.platform = U(GLX.box(70, 1, 60));
    meshes.lasers = U(GLX.lines([[-300, 0, 0, 300, 0, 0], [0, -ISO_H, 0, 0, 200, 0], [0, 0, -260, 0, 0, 260]]));
  }
  // loft each "track" (trunk, left / right limb or breast) of a list-of-ellipses function
  function tracksMesh(fn, z0, z1, dz, n) {
    const tracks = {};
    for (let z = z0; z <= z1 + 1e-6; z += dz) {
      const E = fn(Math.max(z0 + 0.3, Math.min(z1 - 0.3, z)));
      for (const e of E) {
        const key = Math.abs(e.cx) > 1 ? (e.cx > 0 ? "L" : "R") : "C";
        (tracks[key] = tracks[key] || []).push({ z, pts: Array.from({ length: n }, (_, i) => { const t = i / n * 2 * Math.PI; return [e.cx + e.a * Math.cos(t), e.cy + e.b * Math.sin(t)]; }) });
      }
    }
    return Object.values(tracks).filter(r => r.length > 1).map(r => GLX.upload(ctx, GLX.loft(r)));
  }
  function freePatient() {
    if (!patient) return;
    for (const m of [...patient.body, ...patient.lungs, ...patient.targets]) { ctx.gl.deleteBuffer(m.bp); ctx.gl.deleteBuffer(m.bn); ctx.gl.deleteBuffer(m.bi); }
  }
  function buildPatient() {
    if (!ctx) return;
    freePatient();
    const ph = CASE.ph, dz = (ph.z1 - ph.z0) > 100 ? 1.5 : 1;
    patient = { id: ph.id, body: tracksMesh(z => ph.body(z), ph.z0, ph.z1, dz, 40), lungs: tracksMesh(z => ph.lungs(z), ph.z0, ph.z1, 0.8, 28), targets: [] };
    // targets of site phantoms as fitted ellipsoids (from the structure masks)
    if (ph.kind !== "tbi") for (const t of CASE.structs.filter(s => s.role === "target")) {
      const sg = CASE.sg; let n = 0, mn = [1e9, 1e9, 1e9], mx = [-1e9, -1e9, -1e9];
      for (let k = 0, q = 0; k < sg.nz; k++) for (let j = 0; j < sg.ny; j++) for (let i = 0; i < sg.nx; i++, q++) if (sg.bits[q] & t.bit) {
        const p = [sg.x0 + (i + 0.5) * sg.h, sg.y0 + (j + 0.5) * sg.h, sg.z0 + (k + 0.5) * sg.h]; n++;
        for (let a = 0; a < 3; a++) { mn[a] = Math.min(mn[a], p[a]); mx[a] = Math.max(mx[a], p[a]); }
      }
      if (!n) continue;
      const c = mn.map((v, a) => (v + mx[a]) / 2), r = mn.map((v, a) => (mx[a] - v) / 2 + sg.h / 2), rings = [];
      for (let s = -1; s <= 1.0001; s += 0.1) { const f = Math.sqrt(Math.max(0.02, 1 - s * s)); rings.push({ z: c[2] + s * r[2], pts: Array.from({ length: 24 }, (_, i) => { const t2 = i / 24 * 2 * Math.PI; return [c[0] + f * r[0] * Math.cos(t2), c[1] + f * r[1] * Math.sin(t2)]; }) }); }
      patient.targets.push(Object.assign(GLX.upload(ctx, GLX.loft(rings)), { color: t.color }));
    }
  }

  function init(cv) {
    canvas = cv;
    try { ctx = GLX.create(cv); } catch (e) { console.error(e); ctx = null; }
    if (!ctx) return false;
    buildStatic();
    let drag = null;
    cv.addEventListener("mousedown", e => { drag = { x: e.clientX, y: e.clientY, b: e.button }; e.preventDefault(); });
    window.addEventListener("mouseup", () => drag = null);
    window.addEventListener("mousemove", e => {
      if (!drag) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.x = e.clientX; drag.y = e.clientY;
      if (drag.b === 0) { cam.yaw -= dx * 0.008; cam.pitch = Math.max(-0.2, Math.min(1.5, cam.pitch + dy * 0.006)); }
      else { cam.tx -= dx * 0.6 * Math.cos(cam.yaw); cam.tz += dx * 0.6 * Math.sin(cam.yaw); cam.ty += dy * 0.6; }
      ROOM.onChange && ROOM.onChange();
    });
    cv.addEventListener("contextmenu", e => e.preventDefault());
    cv.addEventListener("wheel", e => { cam.dist = Math.max(100, Math.min(1500, cam.dist * (1 + Math.sign(e.deltaY) * 0.08))); e.preventDefault(); ROOM.onChange && ROOM.onChange(); }, { passive: false });
    return true;
  }

  // patient -> room matrix for a beam (lying HFS / FFS, or standing for extended-SSD fields)
  const mk = (c0, c1, c2, t) => new Float32Array([...c0, 0, ...c1, 0, ...c2, 0, ...t, 1]);
  function pose(b) {
    const { x: ix, y: iy, z: iz } = b.iso;
    if (b.standing) {
      const D = 100 - (b.sad || 100), pa = Math.abs(((b.gantry % 360) + 360) % 360 - 180) < 90;
      return pa ? mk([0, 0, 1], [1, 0, 0], [0, -1, 0], [-iy + D, iz, -ix]) : mk([0, 0, -1], [-1, 0, 0], [0, -1, 0], [iy + D, iz, ix]);
    }
    if (b.orient === "FFS") return mk([-1, 0, 0], [0, -1, 0], [0, 0, -1], [ix, iy, iz]);
    return mk([1, 0, 0], [0, -1, 0], [0, 0, 1], [-ix, iy, -iz]);
  }
  const apply = (P, p) => [P[0] * p[0] + P[4] * p[1] + P[8] * p[2] + P[12], P[1] * p[0] + P[5] * p[1] + P[9] * p[2] + P[13], P[2] * p[0] + P[6] * p[1] + P[10] * p[2] + P[14]];

  // st: {cp, plan}
  function render(st) {
    if (!ctx) return;
    if (!patient || patient.id !== CASE.ph.id || patient.v !== CASE.version) { buildPatient(); patient.v = CASE.version; }
    const gl = ctx.gl, W = canvas.clientWidth, H = canvas.clientHeight, dpr = window.devicePixelRatio || 1;
    if (canvas.width !== Math.round(W * dpr) || canvas.height !== Math.round(H * dpr)) { canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr); }
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.clearColor(0.075, 0.09, 0.115, 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    const eye = [cam.tx + cam.dist * Math.cos(cam.pitch) * Math.sin(cam.yaw), cam.ty + cam.dist * Math.sin(cam.pitch), cam.tz + cam.dist * Math.cos(cam.pitch) * Math.cos(cam.yaw)];
    const vp = M.mul(M.persp(0.62, W / Math.max(1, H), 5, 4000), M.lookAt(eye, [cam.tx, cam.ty, cam.tz], [0, 1, 0]));
    const D = (mesh, model, col, lit = 1) => GLX.draw(ctx, mesh, model, vp, eye, col, lit);
    const temps = [], T = m => { const u = GLX.upload(ctx, m); temps.push(u); return u; };
    const plan = st.plan, cp = st.cp, b = cp ? plan.beams[cp.beam] : plan.beams.find(q => !q.off) || plan.beams[0];
    if (!b) return;
    const standing = !!b.standing, roomTheta = standing ? 90 : cp ? cp.theta : b.type === "arc" ? b.start : b.gantry;
    const G = M.rotZ(-roomTheta * Math.PI / 180), P = pose(b);
    gl.disable(gl.BLEND); gl.depthMask(true);
    if (opts.showRoom) { D(meshes.floor, M.trans(0, -ISO_H - 1, 40), [0.19, 0.21, 0.25, 1]); D(meshes.wall, M.trans(0, 30, -205), [0.15, 0.17, 0.21, 1]); }
    D(meshes.stand, M.trans(0, -ISO_H + 125, -158), GLX.hex("#d9dde3"));
    D(meshes.drum, M.chain(M.trans(0, 0, -118), G), GLX.hex("#c9ced6"));
    D(meshes.drumRing, M.chain(M.trans(0, 0, -112), G), GLX.hex("#2b3442"));
    D(meshes.arm, M.chain(G, M.trans(0, 112, -60)), GLX.hex("#e6e9ee"));
    D(meshes.head, M.chain(G, M.trans(0, 92, 0)), GLX.hex("#eef0f3"));
    D(meshes.headNose, M.chain(G, M.trans(0, 66, 0), M.rotX(-Math.PI / 2)), GLX.hex("#b9c1cc"));
    D(meshes.panelArm, M.chain(G, M.trans(0, -58, -50)), GLX.hex("#9aa3af"));
    D(meshes.panel, M.chain(G, M.trans(0, -55, 0)), GLX.hex("#3d4654"));
    // couch, or a standing platform for extended-SSD set-ups
    const ph = CASE.ph;
    if (standing) {
      const feet = apply(P, [b.iso.x, b.iso.y, ph.z1]), h = Math.max(2, feet[1] + ISO_H);
      D(T(GLX.box(70, h, 60)), M.trans(feet[0], -ISO_H + h / 2, feet[2]), GLX.hex("#7d8796"));
    } else {
      D(meshes.pedestal, M.trans(0, -ISO_H + 45, 150), GLX.hex("#cfd4db"));
      D(meshes.couchBase, M.trans(0, -26, 150), GLX.hex("#b8bfc9"));
      const za = apply(P, [b.iso.x, b.iso.y, ph.z0])[2], zb = apply(P, [b.iso.x, b.iso.y, ph.z1])[2], end = Math.min(za, zb) - 10;
      const top = -(CASE.C.back - b.iso.y) - 2.6, cx = apply(P, [0, b.iso.y, b.iso.z])[0];
      D(meshes.couchTop, M.trans(cx, top, end + 107.5), [0.22, 0.24, 0.27, 1]);
    }
    // isocentre markers (all isocentres seen in this patient position)
    const seen = new Set();
    plan.beams.forEach(q => {
      if (q.off || q.orient !== b.orient || !!q.standing !== standing) return;
      const k = `${q.iso.x},${q.iso.y},${q.iso.z}`; if (seen.has(k)) return; seen.add(k);
      const p = apply(P, [q.iso.x, q.iso.y, q.iso.z]), cur = q.iso.x === b.iso.x && q.iso.y === b.iso.y && q.iso.z === b.iso.z;
      D(meshes.isoMark, M.trans(...p), cur ? GLX.hex("#ff5a4f") : GLX.hex("#58a6ff"), 0);
    });
    if (opts.transparent) { for (const m of patient.lungs) D(m, P, GLX.hex("#4fa3ff")); for (const m of patient.targets) D(m, P, GLX.hex(m.color)); }
    if (opts.showLasers) D(meshes.lasers, M.ident(), [0.2, 1.0, 0.35, 1], 0);
    gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    // arc tracks and static field directions
    if (opts.showTracks && !standing) {
      const done = new Set();
      plan.beams.forEach((q, qi) => {
        if (q.off || q.orient !== b.orient || q.standing) return;
        const zc = apply(P, [q.iso.x, q.iso.y, q.iso.z])[2], cur = cp && cp.beam === qi;
        if (q.type === "arc") {
          const key = zc.toFixed(1); if (!done.has(key)) {
            done.add(key); const segs = [], n = 90;
            for (let k = 0; k < n; k++) { const a0 = k / n * 2 * Math.PI, a1 = (k + 1) / n * 2 * Math.PI; segs.push([100 * Math.sin(a0), 100 * Math.cos(a0), zc, 100 * Math.sin(a1), 100 * Math.cos(a1), zc]); }
            D(T(GLX.lines(segs)), M.ident(), Math.abs(zc) < 0.1 ? [1, 0.62, 0.2, 0.95] : [0.55, 0.7, 1, 0.45], 0);
          }
          if (cur) {
            const sw = [], span = ENG.arcSpan(q), sg = q.dir === "CCW" ? -1 : 1, done2 = (cp.k + 1) / cp.n, n = 90, k1 = Math.max(1, Math.round(n * done2));
            for (let k = 0; k < k1; k++) {
              const a0 = (q.start + sg * span * k / n) * Math.PI / 180, a1 = (q.start + sg * span * (k + 1) / n) * Math.PI / 180;
              for (const r of [98, 100, 102]) sw.push([r * Math.sin(a0), r * Math.cos(a0), zc, r * Math.sin(a1), r * Math.cos(a1), zc]);
            }
            D(T(GLX.lines(sw)), M.ident(), [1, 0.85, 0.2, 1], 0);
          }
        } else if (Math.abs(zc) < 0.1) {
          const a = q.gantry * Math.PI / 180;
          D(T(GLX.lines([[0, 0, zc, 100 * Math.sin(a), 100 * Math.cos(a), zc]])), M.ident(), cur ? [1, 0.75, 0.3, 1] : [0.6, 0.75, 1, 0.7], 0);
        }
      });
    }
    gl.depthMask(!opts.transparent);
    for (const m of patient.body) D(m, P, opts.transparent ? [0.93, 0.78, 0.66, 0.42] : [0.93, 0.78, 0.66, 1]);
    gl.depthMask(true);
    // beam: jaw-defined pyramid from the source to 40 cm beyond the isocentre
    if (opts.showBeam && cp) {
      const sad = cp.sad, L = sad + 40, k = L / sad, S = [0, 100, 0];
      const corners = [[cp.X1, cp.Y1], [cp.X2, cp.Y1], [cp.X2, cp.Y2], [cp.X1, cp.Y2]].map(([X, Y]) => {
        const u = X * cp.cc - Y * cp.cs, w = X * cp.cs + Y * cp.cc;
        return standing ? [w * k, 100 - L, -u * k] : [u * k, 100 - L, w * k];
      });
      const tri = []; for (let i = 0; i < 4; i++) tri.push(S, corners[i], corners[(i + 1) % 4]);
      gl.depthMask(false);
      D(T(GLX.tris(tri)), G, [1.0, 0.55, 0.15, 0.2], 0);
      D(T(GLX.lines([...corners.map(q => [...S, ...q]), ...corners.map((q, i) => [...q, ...corners[(i + 1) % 4]]), [...S, 0, 100 - L, 0]])), G, [1.0, 0.7, 0.3, 0.9], 0);
      gl.depthMask(true);
    }
    gl.disable(gl.BLEND);
    for (const m of temps) { gl.deleteBuffer(m.bp); gl.deleteBuffer(m.bn); gl.deleteBuffer(m.bi); }
  }

  function resetView(which, standing) {
    const v = { iso: [0.95, 0.42, 330], bev: [0.02, 1.45, 380], side: [Math.PI / 2, 0.06, 420], foot: [0.0, 0.12, 400] }[which] || [0.95, 0.42, 330];
    cam.yaw = v[0]; cam.pitch = v[1]; cam.dist = v[2]; cam.tx = 0; cam.ty = -18; cam.tz = 30;
    const len = CASE.ph ? CASE.ph.z1 - CASE.ph.z0 : 90;
    if (len > 100 && which !== "bev") cam.dist *= 1.25;
    if (CASE.ph && CASE.ph.kind !== "tbi") { cam.dist *= 0.8; cam.tz = 0; cam.ty = -10; }
    if (standing) { cam.tx = -150; cam.ty = -10; cam.tz = 0; cam.dist = Math.max(cam.dist, 720); if (which === "iso" || !which) { cam.yaw = 0.6; cam.pitch = 0.25; } }
  }
  return { init, render, opts, resetView, onChange: null, buildPatient, get ok() { return !!ctx; }, get patient() { return patient; } };
})();
