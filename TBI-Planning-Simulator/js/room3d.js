/* TBI Planning Simulator — 3D treatment-room view (generic linac, couch, phantom, beam, arc tracks). */
"use strict";
const ROOM = (() => {
  const { M } = GLX;
  let ctx = null, canvas = null, meshes = {}, cam = { yaw: 0.95, pitch: 0.42, dist: 330, tx: 0, ty: -18, tz: 30 };
  const ISO_H = 127;                                   // isocentre height above floor (cm)
  const opts = { transparent: true, showTracks: true, showBeam: true, showLasers: true, showRoom: true };

  function patientToRoom(x, y, z, shift) { return [x, -y, z - shift]; }

  function buildStatic() {
    const U = m => GLX.upload(ctx, m);
    meshes.floor = U(GLX.box(700, 2, 700));
    meshes.wall = U(GLX.box(700, 320, 2));
    meshes.stand = U(GLX.box(190, 250, 70));
    meshes.drum = U(GLX.cyl(92, 10, 64));
    meshes.drumRing = U(GLX.cyl(70, 11, 64));
    meshes.arm = U(GLX.box(56, 30, 120));
    meshes.head = U(GLX.box(64, 40, 62));
    meshes.headNose = U(GLX.cyl(30, 22, 48, 24));
    meshes.panel = U(GLX.box(44, 3, 44));
    meshes.panelArm = U(GLX.box(8, 8, 95));
    meshes.pedestal = U(GLX.box(46, 90, 60));
    meshes.couchBase = U(GLX.box(70, 12, 120));
    meshes.couchTop = U(GLX.box(53, 5, 215));
    meshes.isoMark = U(GLX.box(2.4, 2.4, 2.4));
    // phantom (patient frame, y flipped to room "up")
    const rings = [];
    for (let z = 0; z <= PH.LENGTH; z += 1) {
      const zz = Math.max(0.6, Math.min(PH.LENGTH, z));
      rings.push({ z: zz, pts: PH.ring(zz, 40).map(([x, y]) => [x, -y]) });
    }
    meshes.body = U(GLX.loft(rings));
    const lungRings = side => {
      const r = [];
      for (let z = 29.2; z <= 52.8; z += 0.8) {
        const L = PH.lungs(z); if (!L.length) continue;
        const e = L[side]; const pts = [];
        for (let i = 0; i < 28; i++) { const t = i / 28 * Math.PI * 2; pts.push([e.cx + e.a * Math.cos(t), -(e.cy + e.b * Math.sin(t))]); }
        r.push({ z, pts });
      }
      return r;
    };
    meshes.lungR = U(GLX.loft(lungRings(0)));
    meshes.lungL = U(GLX.loft(lungRings(1)));
    meshes.lasers = U(GLX.lines([[-300, 0, 0, 300, 0, 0], [0, -ISO_H, 0, 0, 200, 0], [0, 0, -260, 0, 0, 260]]));
  }

  function init(cv) {
    canvas = cv;
    try { ctx = GLX.create(cv); } catch (e) { console.error(e); ctx = null; }
    if (!ctx) return false;
    buildStatic();
    // orbit / zoom / pan
    let drag = null;
    cv.addEventListener("mousedown", e => { drag = { x: e.clientX, y: e.clientY, b: e.button }; e.preventDefault(); });
    window.addEventListener("mouseup", () => drag = null);
    window.addEventListener("mousemove", e => {
      if (!drag) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.x = e.clientX; drag.y = e.clientY;
      if (drag.b === 0) { cam.yaw -= dx * 0.008; cam.pitch = Math.max(-0.2, Math.min(1.45, cam.pitch + dy * 0.006)); }
      else { cam.tx -= dx * 0.6 * Math.cos(cam.yaw); cam.tz += dx * 0.6 * Math.sin(cam.yaw); cam.ty += dy * 0.6; }
      ROOM.onChange && ROOM.onChange();
    });
    cv.addEventListener("contextmenu", e => e.preventDefault());
    cv.addEventListener("wheel", e => { cam.dist = Math.max(120, Math.min(1100, cam.dist * (1 + Math.sign(e.deltaY) * 0.08))); e.preventDefault(); ROOM.onChange && ROOM.onChange(); }, { passive: false });
    return true;
  }

  // st: {theta, shift, cp, plan, isoIdx, progress (0..1 of current arc), arcDir}
  function render(st) {
    if (!ctx) return;
    const gl = ctx.gl, W = canvas.clientWidth, H = canvas.clientHeight, dpr = window.devicePixelRatio || 1;
    if (canvas.width !== Math.round(W * dpr) || canvas.height !== Math.round(H * dpr)) { canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr); }
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.clearColor(0.075, 0.09, 0.115, 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    const eye = [cam.tx + cam.dist * Math.cos(cam.pitch) * Math.sin(cam.yaw), cam.ty + cam.dist * Math.sin(cam.pitch),
                 cam.tz + cam.dist * Math.cos(cam.pitch) * Math.cos(cam.yaw)];
    const vp = M.mul(M.persp(0.62, W / H, 5, 3000), M.lookAt(eye, [cam.tx, cam.ty, cam.tz], [0, 1, 0]));
    const D = (mesh, model, col, lit = 1) => GLX.draw(ctx, mesh, model, vp, eye, col, lit);
    const temps = [];
    const T = m => { const u = GLX.upload(ctx, m); temps.push(u); return u; };
    const th = st.theta * Math.PI / 180, G = M.rotZ(-th);
    gl.disable(gl.BLEND); gl.depthMask(true);

    // room
    if (opts.showRoom) {
      D(meshes.floor, M.trans(0, -ISO_H - 1, 40), [0.19, 0.21, 0.25, 1]);
      D(meshes.wall, M.trans(0, 30, -205), [0.15, 0.17, 0.21, 1]);
    }
    // gantry stand (fixed) and rotating parts
    D(meshes.stand, M.trans(0, -ISO_H + 125, -158), GLX.hex("#d9dde3"));
    D(meshes.drum, M.chain(M.trans(0, 0, -118), G), GLX.hex("#c9ced6"));
    D(meshes.drumRing, M.chain(M.trans(0, 0, -112), G), GLX.hex("#2b3442"));
    D(meshes.arm, M.chain(G, M.trans(0, 112, -60)), GLX.hex("#e6e9ee"));
    D(meshes.head, M.chain(G, M.trans(0, 92, 0)), GLX.hex("#eef0f3"));
    D(meshes.headNose, M.chain(G, M.trans(0, 66, 0), M.rotX(-Math.PI / 2)), GLX.hex("#b9c1cc"));
    D(meshes.panelArm, M.chain(G, M.trans(0, -58, -50)), GLX.hex("#9aa3af"));
    D(meshes.panel, M.chain(G, M.trans(0, -55, 0)), GLX.hex("#3d4654"));
    // couch (moves longitudinally with the shift; patient head towards the gantry)
    D(meshes.pedestal, M.trans(0, -ISO_H + 45, 150), GLX.hex("#cfd4db"));
    D(meshes.couchBase, M.trans(0, -26, 150), GLX.hex("#b8bfc9"));
    const back = 11.4;
    D(meshes.couchTop, M.trans(0, -back - 2.6, 97.5 - st.shift), [0.22, 0.24, 0.27, 1]);

    const P = M.trans(0, 0, -st.shift);
    // isocentre markers
    st.plan.isos.forEach((iso, i) => D(meshes.isoMark, M.chain(P, M.trans(0, 0, iso.z)), i === st.isoIdx ? GLX.hex("#ff5a4f") : GLX.hex("#58a6ff"), 0));
    // lungs (visible through the transparent body)
    if (opts.transparent) {
      D(meshes.lungR, P, GLX.hex("#4fa3ff")); D(meshes.lungL, P, GLX.hex("#a07bff"));
    }
    if (opts.showLasers) D(meshes.lasers, M.ident(), [0.2, 1.0, 0.35, 1], 0);

    // arc tracks (one per isocentre, machine plane shifted with the couch)
    gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    if (opts.showTracks) {
      st.plan.isos.forEach((iso, i) => {
        const segs = [], z = iso.z - st.shift, n = 90;
        for (let k = 0; k < n; k++) {
          const a0 = k / n * 2 * Math.PI, a1 = (k + 1) / n * 2 * Math.PI;
          segs.push([100 * Math.sin(a0), 100 * Math.cos(a0), z, 100 * Math.sin(a1), 100 * Math.cos(a1), z]);
        }
        const m = T(GLX.lines(segs));
        D(m, M.ident(), i === st.isoIdx ? [1, 0.62, 0.2, 0.95] : [0.55, 0.7, 1, 0.45], 0);
        // swept part of the current arc
        if (i === st.isoIdx && st.progress > 0) {
          const sw = [], k1 = Math.max(1, Math.round(n * st.progress));
          for (let k = 0; k < k1; k++) {
            const a0 = ((180 + st.arcDir * k / n * 360) * Math.PI / 180), a1 = ((180 + st.arcDir * (k + 1) / n * 360) * Math.PI / 180);
            for (const r of [98, 100, 102]) sw.push([r * Math.sin(a0), r * Math.cos(a0), z, r * Math.sin(a1), r * Math.cos(a1), z]);
          }
          D(T(GLX.lines(sw)), M.ident(), [1, 0.85, 0.2, 1], 0);
        }
      });
    }
    // phantom body
    gl.depthMask(!opts.transparent);
    D(meshes.body, P, opts.transparent ? [0.93, 0.78, 0.66, 0.42] : [0.93, 0.78, 0.66, 1]);
    gl.depthMask(true);
    // beam (jaw-defined pyramid, source to 40 cm beyond the isocentre)
    if (opts.showBeam && st.cp) {
      const cp = st.cp, L = 140, k = L / 100, S = [0, 100, 0];
      const c = [[-20 * k, 100 - L, cp.wlo * k], [20 * k, 100 - L, cp.wlo * k], [20 * k, 100 - L, cp.whi * k], [-20 * k, 100 - L, cp.whi * k]];
      const tri = [];
      for (let i = 0; i < 4; i++) tri.push(S, c[i], c[(i + 1) % 4]);
      const beam = T(GLX.tris(tri));
      gl.depthMask(false);
      D(beam, G, [1.0, 0.55, 0.15, 0.22], 0);
      const edges = T(GLX.lines([...c.map(q => [...S, ...q]), ...c.map((q, i) => [...q, ...c[(i + 1) % 4]]), [...S, 0, -40, 0]]));
      D(edges, G, [1.0, 0.7, 0.3, 0.9], 0);
      gl.depthMask(true);
    }
    gl.disable(gl.BLEND);
    for (const m of temps) { gl.deleteBuffer(m.bp); gl.deleteBuffer(m.bn); gl.deleteBuffer(m.bi); }
  }

  function resetView(which) {
    const v = { iso: [0.95, 0.42, 330], bev: [0.02, 1.45, 380], side: [Math.PI / 2, 0.06, 420], foot: [0.0, 0.12, 400] }[which] || [0.95, 0.42, 330];
    cam.yaw = v[0]; cam.pitch = v[1]; cam.dist = v[2]; cam.tx = 0; cam.ty = -18; cam.tz = 30;
  }
  return { init, render, opts, resetView, onChange: null, get ok() { return !!ctx; } };
})();
