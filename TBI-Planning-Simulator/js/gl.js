/* TBI Planning Simulator — minimal WebGL 1 renderer (no external libraries, works offline). */
"use strict";
const GLX = (() => {
  // ------------------------------------------------------------- 4x4 matrices (column-major)
  const M = {
    ident() { return new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]); },
    mul(a, b) {
      const o = new Float32Array(16);
      for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) {
        let s = 0; for (let k = 0; k < 4; k++) s += a[k * 4 + r] * b[c * 4 + k];
        o[c * 4 + r] = s;
      }
      return o;
    },
    persp(fovy, asp, n, f) {
      const t = 1 / Math.tan(fovy / 2), o = new Float32Array(16);
      o[0] = t / asp; o[5] = t; o[10] = (f + n) / (n - f); o[11] = -1; o[14] = 2 * f * n / (n - f);
      return o;
    },
    lookAt(e, c, up) {
      let zx = e[0] - c[0], zy = e[1] - c[1], zz = e[2] - c[2];
      let l = Math.hypot(zx, zy, zz); zx /= l; zy /= l; zz /= l;
      let xx = up[1] * zz - up[2] * zy, xy = up[2] * zx - up[0] * zz, xz = up[0] * zy - up[1] * zx;
      l = Math.hypot(xx, xy, xz); xx /= l; xy /= l; xz /= l;
      const yx = zy * xz - zz * xy, yy = zz * xx - zx * xz, yz = zx * xy - zy * xx;
      return new Float32Array([xx, yx, zx, 0, xy, yy, zy, 0, xz, yz, zz, 0,
        -(xx * e[0] + xy * e[1] + xz * e[2]), -(yx * e[0] + yy * e[1] + yz * e[2]), -(zx * e[0] + zy * e[1] + zz * e[2]), 1]);
    },
    trans(x, y, z) { const o = M.ident(); o[12] = x; o[13] = y; o[14] = z; return o; },
    scale(x, y, z) { const o = M.ident(); o[0] = x; o[5] = y; o[10] = z; return o; },
    rotZ(a) { const c = Math.cos(a), s = Math.sin(a), o = M.ident(); o[0] = c; o[1] = s; o[4] = -s; o[5] = c; return o; },
    rotX(a) { const c = Math.cos(a), s = Math.sin(a), o = M.ident(); o[5] = c; o[6] = s; o[9] = -s; o[10] = c; return o; },
    rotY(a) { const c = Math.cos(a), s = Math.sin(a), o = M.ident(); o[0] = c; o[2] = -s; o[8] = s; o[10] = c; return o; },
    chain(...ms) { return ms.reduce((a, b) => M.mul(a, b)); },
  };

  const VS = `attribute vec3 p; attribute vec3 n; uniform mat4 mvp; uniform mat4 model; varying vec3 vn; varying vec3 vw;
    void main(){ vn = mat3(model) * n; vw = (model * vec4(p,1.0)).xyz; gl_Position = mvp * vec4(p,1.0); }`;
  const FS = `precision mediump float; varying vec3 vn; varying vec3 vw; uniform vec4 col; uniform float lit; uniform vec3 eye;
    void main(){ vec3 N = normalize(vn); vec3 L = normalize(vec3(0.35,0.8,0.45)); vec3 L2 = normalize(vec3(-0.6,0.3,-0.5));
      float d = max(dot(N,L),0.0)*0.65 + max(dot(N,L2),0.0)*0.25 + 0.28;
      vec3 V = normalize(eye - vw); float sp = pow(max(dot(reflect(-L,N),V),0.0), 24.0) * 0.18;
      vec3 c = mix(col.rgb, col.rgb * d + sp, lit); gl_FragColor = vec4(c, col.a); }`;

  function create(canvas) {
    const gl = canvas.getContext("webgl", { antialias: true, preserveDrawingBuffer: true }) ||
               canvas.getContext("experimental-webgl", { preserveDrawingBuffer: true });
    if (!gl) return null;
    const sh = (t, s) => { const o = gl.createShader(t); gl.shaderSource(o, s); gl.compileShader(o);
      if (!gl.getShaderParameter(o, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(o)); return o; };
    const prog = gl.createProgram();
    gl.attachShader(prog, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FS));
    gl.linkProgram(prog); gl.useProgram(prog);
    const loc = { p: gl.getAttribLocation(prog, "p"), n: gl.getAttribLocation(prog, "n"),
      mvp: gl.getUniformLocation(prog, "mvp"), model: gl.getUniformLocation(prog, "model"),
      col: gl.getUniformLocation(prog, "col"), lit: gl.getUniformLocation(prog, "lit"), eye: gl.getUniformLocation(prog, "eye") };
    gl.enable(gl.DEPTH_TEST);
    return { gl, prog, loc };
  }

  // mesh: {pos:[], nor:[], idx:[], mode}
  function upload(ctx, mesh) {
    const gl = ctx.gl;
    const b = k => { const o = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, o); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(mesh[k]), gl.STATIC_DRAW); return o; };
    mesh.bp = b("pos"); mesh.bn = b("nor");
    mesh.bi = gl.createBuffer(); gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, mesh.bi);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array(mesh.idx), gl.STATIC_DRAW);
    mesh.count = mesh.idx.length;
    return mesh;
  }
  function draw(ctx, mesh, model, vp, eye, color, lit = 1) {
    const gl = ctx.gl, L = ctx.loc;
    gl.uniformMatrix4fv(L.mvp, false, M.mul(vp, model));
    gl.uniformMatrix4fv(L.model, false, model);
    gl.uniform4fv(L.col, color); gl.uniform1f(L.lit, lit); gl.uniform3fv(L.eye, eye);
    gl.bindBuffer(gl.ARRAY_BUFFER, mesh.bp); gl.enableVertexAttribArray(L.p); gl.vertexAttribPointer(L.p, 3, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, mesh.bn); gl.enableVertexAttribArray(L.n); gl.vertexAttribPointer(L.n, 3, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, mesh.bi);
    gl.drawElements(mesh.mode === "lines" ? gl.LINES : gl.TRIANGLES, mesh.count, gl.UNSIGNED_SHORT, 0);
  }

  // ------------------------------------------------------------- geometry builders
  function box(sx, sy, sz) {
    const pos = [], nor = [], idx = [];
    const f = (n, u, v) => {
      const o = pos.length / 3;
      for (const [a, b] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) {
        pos.push((n[0] + u[0] * a + v[0] * b) * sx / 2, (n[1] + u[1] * a + v[1] * b) * sy / 2, (n[2] + u[2] * a + v[2] * b) * sz / 2);
        nor.push(...n);
      }
      idx.push(o, o + 1, o + 2, o, o + 2, o + 3);
    };
    f([1, 0, 0], [0, 1, 0], [0, 0, 1]); f([-1, 0, 0], [0, 0, 1], [0, 1, 0]);
    f([0, 1, 0], [0, 0, 1], [1, 0, 0]); f([0, -1, 0], [1, 0, 0], [0, 0, 1]);
    f([0, 0, 1], [1, 0, 0], [0, 1, 0]); f([0, 0, -1], [0, 1, 0], [1, 0, 0]);
    return { pos, nor, idx };
  }
  // cylinder along z, centred, radius r, length h
  function cyl(r, h, n = 40, r2 = r) {
    const pos = [], nor = [], idx = [];
    for (let i = 0; i <= n; i++) {
      const t = i / n * Math.PI * 2, c = Math.cos(t), s = Math.sin(t);
      pos.push(r * c, r * s, -h / 2, r2 * c, r2 * s, h / 2); nor.push(c, s, 0, c, s, 0);
    }
    for (let i = 0; i < n; i++) { const a = 2 * i; idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
    for (const [zz, rr, nz] of [[-h / 2, r, -1], [h / 2, r2, 1]]) {
      const o = pos.length / 3; pos.push(0, 0, zz); nor.push(0, 0, nz);
      for (let i = 0; i <= n; i++) { const t = i / n * Math.PI * 2; pos.push(rr * Math.cos(t), rr * Math.sin(t), zz); nor.push(0, 0, nz); }
      for (let i = 0; i < n; i++) nz > 0 ? idx.push(o, o + 1 + i, o + 2 + i) : idx.push(o, o + 2 + i, o + 1 + i);
    }
    return { pos, nor, idx };
  }
  // loft through rings: rings = [{z, pts:[[x,y]...]}] (same point count), closed caps
  function loft(rings) {
    const pos = [], nor = [], idx = [], m = rings[0].pts.length;
    rings.forEach((r, k) => {
      r.pts.forEach(([x, y], i) => {
        const a = r.pts[(i + 1) % m], b = r.pts[(i + m - 1) % m];
        let nx = a[1] - b[1], ny = -(a[0] - b[0]); const l = Math.hypot(nx, ny) || 1;
        pos.push(x, y, r.z); nor.push(nx / l, ny / l, 0);
      });
    });
    for (let k = 0; k < rings.length - 1; k++) for (let i = 0; i < m; i++) {
      const a = k * m + i, b = k * m + (i + 1) % m, c = (k + 1) * m + i, d = (k + 1) * m + (i + 1) % m;
      idx.push(a, c, b, b, c, d);
    }
    return { pos, nor, idx };
  }
  function lines(segs) { // segs: [[x1,y1,z1,x2,y2,z2],...]
    const pos = [], nor = [], idx = [];
    segs.forEach((s, i) => { pos.push(...s); nor.push(0, 1, 0, 0, 1, 0); idx.push(2 * i, 2 * i + 1); });
    return { pos, nor, idx, mode: "lines" };
  }
  function tris(vs) { // flat triangles: [[x,y,z]x3,...] with computed normals
    const pos = [], nor = [], idx = [];
    for (let i = 0; i < vs.length; i += 3) {
      const [a, b, c] = [vs[i], vs[i + 1], vs[i + 2]];
      const u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]], v = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
      let n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]];
      const l = Math.hypot(...n) || 1; n = n.map(q => q / l);
      for (const p of [a, b, c]) { pos.push(...p); nor.push(...n); }
      idx.push(i, i + 1, i + 2);
    }
    return { pos, nor, idx };
  }
  const hex = (h, a = 1) => [parseInt(h.slice(1, 3), 16) / 255, parseInt(h.slice(3, 5), 16) / 255, parseInt(h.slice(5, 7), 16) / 255, a];

  return { M, create, upload, draw, box, cyl, loft, lines, tris, hex };
})();
