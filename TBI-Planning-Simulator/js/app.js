/* RT Planning Simulator — user interface: workflow tabs, beams, cost functions, evaluation and interaction. */
"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const S = {
    cross: { x: 0, y: 0.8, z: 42.5 }, window: { c: 40, w: 400 }, doseMode: "iso",
    isoLevels: { 110: 1, 105: 1, 100: 1, 95: 1, 90: 1, 80: 1, 50: 1, 30: 0 },
    showBeams: true, showMLC: true, cpIndex: 0, cp: null, segIndex: 0, doseVersion: 0, playing: false, panel: "dvh",
    doseSrc: { kind: "plan" }, snapshots: [], compare: new Set(), points: [], profAxis: "z", brush: null, editStruct: "", tool: "",
    selBeam: 0, structDirty: false,
  };
  const views = { ax: new V2.SliceView($("cAx"), "axial"), cor: new V2.SliceView($("cCor"), "coronal"), sag: new V2.SliceView($("cSag"), "sagittal") };
  const bev = new V2.BEV($("cBEV"));
  let snapId = 0;

  function busy(on, text) { $("busy").classList.toggle("on", !!on); if (text) $("busyText").textContent = text; }
  function later(fn) { setTimeout(fn, 30); }
  const plan = () => ENG.state.plan;

  // ------------------------------------------------------------------ render queue
  let pending = new Set(), raf = 0;
  function req(...what) { what.forEach(w => pending.add(w)); if (!raf) raf = requestAnimationFrame(flush); }
  function flush() {
    raf = 0; const p = pending; pending = new Set();
    try {
      if (p.has("room")) renderRoom();
      if (p.has("bev")) bev.draw(S);
      if (p.has("ax")) views.ax.draw(S);
      if (p.has("cor")) views.cor.draw(S);
      if (p.has("sag")) views.sag.draw(S);
      if (p.has("dvh")) renderPanel();
    } catch (e) { console.error(e); }
  }
  const ALL = ["room", "bev", "ax", "cor", "sag", "dvh"];
  function renderRoom() {
    const cp = S.cp, P = plan();
    ROOM.render({ cp, plan: P });
    if (!cp) { $("roomInfo").innerHTML = ""; return; }
    const b = P.beams[cp.beam];
    $("roomInfo").innerHTML = (b.standing ? `Gantry <b>90°</b> (horizontal beam) · patient standing at <b>${b.sad} cm</b>, ${cp.theta === 0 ? "AP" : "PA"}<br>`
      : `Gantry <b>${cp.theta.toFixed(1)}°</b> · Collimator <b>${b.coll || 0}°</b> · Couch <b>0°</b> · <b>${b.orient}</b><br>`) +
      `Isocentre x ${b.iso.x.toFixed(1)}, y ${b.iso.y.toFixed(1)}, z ${b.iso.z.toFixed(1)} cm<br>${esc(b.name)} · ${b.type === "arc" ? `arc ${b.dir} · CP ${cp.k + 1}/${cp.n}` : "static field"} · ${b.energy}`;
  }
  let statsCache = null;
  function stats() { if (!statsCache) statsCache = ENG.stats(); return statsCache; }
  function compareSnaps() { return S.snapshots.filter(s => S.compare.has(s.id)); }
  function renderPanel() {
    if (S.panel === "dvh") V2.drawDVH($("cDVH"), stats(), S, compareSnaps());
    else V2.drawProfile($("cProf"), S, compareSnaps().map(s => ({ axis: s.profAxis, pts: s.profile })));
  }
  function invalidate() { statsCache = null; S.doseVersion++; }

  // ------------------------------------------------------------------ control points
  function setCP(i) {
    const cps = ENG.state.cps;
    if (!cps.length) { S.cp = null; $("cpInfo").textContent = "No active beams"; req(...ALL); return; }
    S.cpIndex = Math.max(0, Math.min(cps.length - 1, i));
    S.cp = cps[S.cpIndex];
    const b = plan().beams[S.cp.beam], nseg = S.cp.segs ? S.cp.segs.length : 1;
    S.segIndex = Math.min(S.segIndex, nseg - 1);
    $("cpSlider").max = cps.length - 1; $("cpSlider").value = S.cpIndex;
    $("segSlider").max = Math.max(0, nseg - 1); $("segSlider").value = S.segIndex; $("segSlider").disabled = nseg < 2;
    const f = ENG.state.scale * 100 / plan().fx * (S.cp.sad / 100) ** 2;
    const mu = S.cp.segs ? S.cp.segs.reduce((a, s) => a + s.w, 0) * f : Math.max(...S.cp.Fs) * f;
    $("cpInfo").textContent = `CP ${S.cpIndex + 1}/${cps.length} · ${b.name} · gantry ${S.cp.theta.toFixed(1)}° · ${S.cp.segs ? `${nseg} segment${nseg > 1 ? "s" : ""}` : "fluence"} · ≈${mu.toFixed(1)} MU`;
    req("room", "bev", "ax");
  }
  let playTimer = 0;
  function play(on) {
    S.playing = on; $("btnPlay").querySelector(".ic").textContent = on ? "⏸" : "▶"; $("btnPlay").querySelector(".tx").textContent = on ? " Pause" : " Play";
    clearTimeout(playTimer); if (!on) return;
    const tick = () => {
      if (!S.playing) return;
      const cps = ENG.state.cps; if (!cps.length) return;
      const next = (S.cpIndex + 1) % cps.length, jump = cps[next].beam !== S.cp.beam;
      setCP(next);
      if (jump && Math.abs(S.cross.z - cps[next].iz) > 1) { S.cross.z = cps[next].iz; req("ax"); }
      playTimer = setTimeout(tick, jump ? 900 : cps[next].n > 1 ? 110 : 600);
    };
    tick();
  }

  // ------------------------------------------------------------------ case and plan loading
  function fillPhantoms() {
    $("phantom").innerHTML = PHANTOMS.LIST.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join("");
    $("quickPreset").innerHTML = PLANS.LIST.map(p => `<option value="${p.id}">${esc(p.label)}</option>`).join("");
  }
  function fillPresets(phId) {
    $("preset").innerHTML = PLANS.forPhantom(phId).map(p => `<option value="${p.id}">${esc(p.label)}</option>`).join("");
    const ph = PHANTOMS.byId[phId];
    $("phantomInfo").innerHTML = `${esc(ph.desc)}.<br>Length ${(ph.z1 - ph.z0).toFixed(0)} cm · width ${(ph.xr[1] - ph.xr[0]).toFixed(0)} cm · ${ph.kind === "tbi" ? "whole-body (TBI)" : "site phantom"}`;
  }
  function loadTemplate(id) {
    const pr = PLANS.byId[id]; if (!pr) return;
    play(false);
    busy(true, `Loading ${pr.label}…`);
    later(() => {
      try {
        if (!CASE.ph || CASE.ph.id !== pr.phantom) {
          CASE.load(pr.phantom); S.snapshots = []; S.compare.clear(); S.points = []; S.doseSrc = { kind: "plan" };
          const c = CASE.ph.cross; S.cross = { x: c.x, y: c.y, z: c.z }; S.profAxis = CASE.ph.kind === "tbi" ? "z" : "x"; $("profAxis").value = S.profAxis;
          ROOM.buildPatient();
        }
        $("phantom").value = pr.phantom; fillPresets(pr.phantom); $("preset").value = id; $("quickPreset").value = id;
        const p = pr.make(); p._template = id;
        if (p.technique === "3D-CRT" || p.technique === "Conventional TBI") { ENG.state.plan = p; ENG.calculate(); } else ENG.setup(p);
        afterSetup();
        ROOM.resetView("iso", p.beams.some(b => b.standing));
      } catch (e) { console.error(e); alert("Could not load: " + e.message); }
      busy(false); invalidate(); refreshAll(); isoChecks(); setCP(0);
    });
  }
  function rebuild(msg, keepCP) {
    play(false);
    busy(true, msg || "Preparing beams and dose influence…");
    later(() => {
      try { if (["3D-CRT", "Conventional TBI"].includes(plan().technique)) ENG.calculate(); else ENG.setup(plan()); afterSetup(); }
      catch (e) { console.error(e); alert(e.message); }
      busy(false); invalidate(); refreshAll(); setCP(keepCP ? S.cpIndex : 0);
    });
  }
  function afterSetup() { S.structDirty = false; $("structDirty").textContent = ""; }
  function refreshAll() {
    planInfo(); structTable(); beamList(); beamEditor(); overlapInfo(); rxForm(); objTable(); paramForm(); optStatus(); evalTables(); snapList(); shiftOptions();
    req(...ALL);
  }
  function planInfo() {
    const P = plan(), parts = new Set(P.beams.map(b => b.part || 1));
    $("planInfo").innerHTML = `<b>${esc(P.name)}</b> · ${P.technique}<br>${P.beams.filter(b => !b.off).length} beams, ${ENG.state.cps.length} control points · Rx ${P.rx} Gy / ${P.fx} fx · target ${esc(P.target)}` +
      (parts.size > 1 ? `<br>Two parts (e.g. head-first and feet-first): optimise one part with the other as a bias dose in step 7.` : "");
    $("techInfo").textContent = `(${P.technique})`;
  }

  // ------------------------------------------------------------------ 2 · structures
  function structTable() {
    const tb = $("structTable").tBodies[0]; tb.innerHTML = "";
    CASE.structs.forEach((s, i) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td><input type="checkbox" ${s.visible ? "checked" : ""} data-k="vis"></td>
        <td><span class="sw" style="background:${s.color}"></span>${esc(s.id)}</td>
        <td>${s.role === "body" ? "external" : `<select data-k="role"><option value="target" ${s.role === "target" ? "selected" : ""}>target</option><option value="oar" ${s.role === "oar" ? "selected" : ""}>OAR</option><option value="other" ${s.role === "other" ? "selected" : ""}>other</option></select>`}</td>
        <td><input type="number" step="0.05" value="${s.rho ?? ""}" data-k="rho" placeholder="CT" style="width:46px"></td>
        <td class="num">${CASE.volume(s.id).toFixed(0)}</td>
        <td>${i > 1 ? `<button data-up title="Move up (higher priority)">▲</button>` : ""}${i > 0 && i < CASE.structs.length - 1 ? `<button data-dn title="Move down">▼</button>` : ""}</td>`;
      tr.querySelector("[data-k=vis]").onchange = e => { s.visible = e.target.checked; bev.cache = {}; req("ax", "cor", "sag", "dvh", "bev"); };
      const r = tr.querySelector("[data-k=role]"); if (r) r.onchange = e => { s.role = e.target.value; markDirty(); };
      tr.querySelector("[data-k=rho]").onchange = e => { s.rho = e.target.value === "" ? null : +e.target.value; CASE.C._densDirty = true; markDirty(); };
      const up = tr.querySelector("[data-up]"); if (up) up.onclick = () => { CASE.structs.splice(i - 1, 0, CASE.structs.splice(i, 1)[0]); structTable(); markDirty(); };
      const dn = tr.querySelector("[data-dn]"); if (dn) dn.onclick = () => { CASE.structs.splice(i + 1, 0, CASE.structs.splice(i, 1)[0]); structTable(); markDirty(); };
      tb.appendChild(tr);
    });
    $("layering").checked = !!plan().layering;
    const opts = CASE.structs.map(s => `<option>${esc(s.id)}</option>`).join(""), all = CASE.names().map(n => `<option>${esc(n)}</option>`).join("");
    const keep = S.editStruct;
    $("editStruct").innerHTML = `<option value="">—</option>` + CASE.structs.filter(s => s.role !== "body").map(s => `<option>${esc(s.id)}</option>`).join("");
    $("editStruct").value = CASE.find(keep) ? keep : "";
    S.editStruct = $("editStruct").value;
    for (const id of ["mSrc", "bA", "bB"]) { const v = $(id).value; $(id).innerHTML = all; if (v) $(id).value = v; }
    void opts;
  }
  function markDirty() { S.structDirty = true; $("structDirty").textContent = "structures changed — apply to use them in the plan"; }
  function applyStructures() {
    const needDens = CASE.C._densDirty; CASE.C._densDirty = false;
    plan().layering = $("layering").checked;
    if (needDens) { CASE.applyDensity(); rebuild("Density overrides changed: recalculating the beams…"); return; }
    busy(true, "Updating structures…");
    later(() => {
      const st = ENG.state; ENG.retag(st.grid); ENG.computeEff(st.grid, plan()); st.version++;
      if (st.fine) { ENG.retag(st.fine); }
      busy(false); afterSetup(); invalidate(); structTable(); evalTables(); req(...ALL);
    });
  }
  function contourMsg(t) { $("contourMsg").textContent = t; }

  // ------------------------------------------------------------------ 3 · beams
  function beamMU() { try { return ENG.muInfo().perBeam; } catch (e) { return {}; } }
  function beamList() {
    const P = plan(), el = $("beamList"), mu = beamMU(); el.innerHTML = "";
    P.beams.forEach((b, i) => {
      const d = document.createElement("div");
      d.className = (i === S.selBeam ? "sel " : "") + (b.off ? "off" : "");
      const geo = b.type === "arc" ? `${b.dir} ${b.start}→${b.stop}°` : `G ${b.gantry}°`;
      d.innerHTML = `<span>${esc(b.name)} · ${geo} · z ${b.iso.z} · ${b.orient}${(b.part || 1) > 1 ? " · part 2" : ""}</span><span>${mu[i] ? "≈" + mu[i].mu.toFixed(0) + " MU" : b.off ? "off" : ""}</span>`;
      d.onclick = () => { S.selBeam = i; beamList(); beamEditor(); const k = ENG.state.cps.findIndex(c => c.beam === i); if (k >= 0) setCP(k); };
      el.appendChild(d);
    });
  }
  function beamEditor() {
    const P = plan(), b = P.beams[S.selBeam], el = $("beamEditor");
    if (!b) { el.innerHTML = ""; return; }
    const num = (k, v, st = 0.5, w = 60) => `<input type="number" step="${st}" value="${v}" data-k="${k}" style="width:${w}px">`;
    const sel = (k, v, list) => `<select data-k="${k}">${list.map(o => `<option ${String(o) === String(v) ? "selected" : ""}>${o}</option>`).join("")}</select>`;
    el.innerHTML = `
      <label>Name</label><div class="pair"><input type="text" value="${esc(b.name)}" data-k="name" style="width:90px"><label><input type="checkbox" data-k="off" ${b.off ? "" : "checked"}> on</label></div>
      <label>Type</label><div class="pair">${sel("type", b.type, ["arc", "static"])} part ${sel("part", b.part || 1, [1, 2])}</div>
      <label>Orientation</label><div class="pair">${sel("orient", b.orient, ["HFS", "FFS"])} ${sel("energy", b.energy, Object.keys(ENG.ENERGY))}</div>
      <label>Isocentre</label><div class="pair">x ${num("iso.x", b.iso.x)} y ${num("iso.y", b.iso.y)} z ${num("iso.z", b.iso.z)}</div>
      ${b.type === "arc" ? `<label>Arc</label><div class="pair">${num("start", b.start, 1)}→${num("stop", b.stop, 1)} ${sel("dir", b.dir, ["CW", "CCW"])}</div>`
        : `<label>Gantry</label><div class="pair">${num("gantry", b.gantry, 1)} °</div>`}
      <label>Collimator</label><div class="pair">${num("coll", b.coll || 0, 5)} ° · SAD ${num("sad", b.sad || 100, 50)} cm</div>
      <label>Jaws X1 / X2</label><div class="pair">${num("X1", b.X1)} ${num("X2", b.X2)} cm</div>
      <label>Jaws Y1 / Y2</label><div class="pair">${num("Y1", b.Y1)} ${num("Y2", b.Y2)} cm</div>
      <label>MLC</label><div class="pair">${sel("mlc", b.mlc || "optimised", ["optimised", "conformal", "open", "blocks"])} margin ${num("margin", b.margin ?? 0.7, 0.1, 46)}</div>
      ${b.mlc === "blocks" ? `<label>Blocks</label><div class="pair">${sel("blockStruct", b.blockStruct || "Lungs", CASE.names())} T ${num("blockT", b.blockT ?? 0.5, 0.05, 46)} m ${num("blockMargin", b.blockMargin ?? 1, 0.5, 40)}</div>` : ""}
      <label>Wedge</label><div class="pair">${sel("wedge.angle", (b.wedge && b.wedge.angle) || 0, [0, 15, 30, 45, 60])}° ${sel("wedge.dir", (b.wedge && b.wedge.dir) || "+X", ["+X", "-X", "+Y", "-Y"])}</div>
      <label>Weight</label><div class="pair">${num("weight", b.weight ?? 1, 0.05)} ${b.sad > 100 ? `<label><input type="checkbox" data-k="standing" ${b.standing ? "checked" : ""}> standing</label>` : ""}</div>`;
    el.querySelectorAll("[data-k]").forEach(inp => inp.addEventListener("change", () => {
      const k = inp.dataset.k;
      let v = inp.type === "checkbox" ? inp.checked : inp.type === "number" ? +inp.value : inp.value;
      if (k === "off") v = !inp.checked;
      if (["part", "wedge.angle"].includes(k)) v = +v;
      if (k.includes(".")) { const [a, c] = k.split("."); b[a] = Object.assign({}, b[a] || {}, { [c]: v }); } else b[k] = v;
      if (k === "type" || k === "mlc") beamEditor();
      beamList(); overlapInfo(); $("applyBeams").classList.add("primary"); $("applyBeams").textContent = "Apply beams *";
    }));
  }
  function overlapInfo() {
    const G = V2.isoGroups(plan()), out = [];
    for (const g of G) if (g.zhi - g.zlo > 40.01) out.push(`<span class="bad">${esc(g.label)}: field length ${(g.zhi - g.zlo).toFixed(1)} cm exceeds 40 cm</span>`);
    if (CASE.ph.kind === "tbi") {
      for (let i = 0; i < G.length - 1; i++) {
        const ov = G[i].zhi - G[i + 1].zlo;
        out.push(ov >= 0 ? `Overlap ${esc(G[i].label)}–${esc(G[i + 1].label)}: <b>${ov.toFixed(1)} cm</b> (isocentre distance ${(G[i + 1].iso.z - G[i].iso.z).toFixed(1)} cm)`
          : `<span class="bad">GAP ${esc(G[i].label)}–${esc(G[i + 1].label)}: ${(-ov).toFixed(1)} cm (cold band!)</span>`);
      }
      if (G.length) {
        if (G[0].zlo > CASE.ph.z0 + 0.5) out.push(`<span class="bad">Vertex not covered (fields start at z = ${G[0].zlo.toFixed(1)} cm)</span>`);
        if (G[G.length - 1].zhi < CASE.ph.z1 - 0.5) out.push(`<span class="bad">Distal end not covered (fields end at z = ${G[G.length - 1].zhi.toFixed(1)} cm, body ends at ${CASE.ph.z1} cm)</span>`);
      }
    }
    $("overlapInfo").innerHTML = out.join("<br>");
  }
  function addBeam(kind) {
    const P = plan(), ref = P.beams[S.selBeam] || P.beams[0];
    const iso = ref ? { ...ref.iso } : { x: CASE.ph.cross.x, y: CASE.ph.cross.y, z: CASE.ph.cross.z };
    const o = ref ? { energy: ref.energy, orient: ref.orient, X1: ref.X1, X2: ref.X2, Y1: ref.Y1, Y2: ref.Y2, part: ref.part || 1 } : {};
    const b = kind === "arc" ? PLANS.arc(`Arc${P.beams.length + 1}`, iso, "CW", o.X1 ?? -5, o.X2 ?? 5, o.Y1 ?? -5, o.Y2 ?? 5, o)
      : PLANS.fld(`F${P.beams.length + 1}`, iso, 0, o.X1 ?? -5, o.X2 ?? 5, o.Y1 ?? -5, o.Y2 ?? 5, Object.assign(o, { mlc: P.technique === "3D-CRT" ? "conformal" : "optimised" }));
    P.beams.push(b); S.selBeam = P.beams.length - 1; beamList(); beamEditor(); overlapInfo();
  }
  // TBI helper: next isocentre down the body with two arcs and a 2 cm overlap, kept inside the phantom
  function addIso() {
    const P = plan(), G = V2.isoGroups(P).filter(g => g.orient === "HFS"), last = G[G.length - 1];
    const half = 13.5, z = last ? Math.min(last.zhi - 2 + half, CASE.ph.z1 - half) : half;
    if (last && z <= last.iso.z + 1) { alert("No room for another isocentre inside the phantom."); return; }
    const letter = String.fromCharCode(65 + G.length);
    P.beams.push(PLANS.arc(`${letter}1`, { x: 0, y: 0, z: +z.toFixed(1) }, "CW", -20, 20, -half, half), PLANS.arc(`${letter}2`, { x: 0, y: 0, z: +z.toFixed(1) }, "CCW", -20, 20, -half, half));
    S.selBeam = P.beams.length - 2; beamList(); beamEditor(); overlapInfo();
  }

  // ------------------------------------------------------------------ 4 · prescription
  function rxForm() {
    const P = plan();
    $("rx").value = P.rx; $("fx").value = P.fx; $("dpf").textContent = `${(P.rx / P.fx).toFixed(2)} Gy`;
    $("target").innerHTML = CASE.names().map(n => `<option ${n === P.target ? "selected" : ""}>${esc(n)}</option>`).join("");
    $("norm").value = P.norm || "mean"; $("doseRate").value = P.params.maxDoseRate;
  }
  function applyRx() {
    const P = plan(), oldRx = P.rx, tgt = $("target").value;
    P.rx = +$("rx").value; P.fx = Math.max(1, +$("fx").value); P.norm = $("norm").value; P.params.maxDoseRate = +$("doseRate").value;
    if (tgt !== P.target) { P.target = tgt; rebuild("New target: rebuilding…"); return; }
    // rescale the existing plan to the new prescription
    const f = P.rx / oldRx;
    if (f !== 1) { for (const cp of ENG.state.cps) { for (let q = 0; q < cp.F.length; q++) { cp.F[q] *= f; cp.Fs[q] *= f; } if (cp.segs) cp.segs.forEach(s => s.w *= f); } for (const g of [ENG.state.grid, ENG.state.fine]) if (g) for (let v = 0; v < g.n; v++) g.dose[v] *= f; }
    invalidate(); rxForm(); planInfo(); evalTables(); isoChecks(); req(...ALL);
  }

  // ------------------------------------------------------------------ 5 · cost functions
  function objTable() {
    const P = plan(), tb = $("objTable").tBodies[0]; tb.innerHTML = "";
    const names = CASE.names();
    P.objectives.forEach((ob, i) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td><input type="checkbox" ${ob.on ? "checked" : ""} data-k="on"></td>
        <td><select data-k="struct">${names.map(s => `<option ${s === ob.struct ? "selected" : ""}>${esc(s)}</option>`).join("")}</select></td>
        <td><select data-k="type">${ENG.OBJ_TYPES.map(s => `<option ${s === ob.type ? "selected" : ""}>${s}</option>`).join("")}</select></td>
        <td><input type="number" step="0.1" value="${ob.dose}" data-k="dose"></td><td><input type="number" step="0.5" value="${ob.extra}" data-k="extra" style="width:40px"></td>
        <td><input type="number" step="0.1" value="${ob.weight}" data-k="weight" style="width:38px"></td>
        <td><select data-k="mode"><option value="objective" ${ob.mode !== "constraint" ? "selected" : ""}>obj</option><option value="constraint" ${ob.mode === "constraint" ? "selected" : ""}>con</option></select></td>
        <td><button data-del title="Remove">✕</button></td>`;
      tr.querySelectorAll("[data-k]").forEach(el => el.addEventListener("change", () => {
        const k = el.dataset.k; ob[k] = k === "on" ? el.checked : ["struct", "type", "mode"].includes(k) ? el.value : +el.value;
        if (k === "type") { const H = ENG.OBJ_HELP[ob.type]; showHelp(ob.type); void H; }
        delete ob._mult;
      }));
      tr.querySelector("[data-k=type]").addEventListener("focus", () => showHelp(ob.type));
      tr.querySelector("[data-del]").onclick = () => { P.objectives.splice(i, 1); objTable(); };
      tb.appendChild(tr);
    });
  }
  function showHelp(t) { const h = ENG.OBJ_HELP[t]; $("objHelp").innerHTML = h ? `<b>${t}</b>: Dose = ${h[0]}, Par. = ${h[1]}` : ""; }

  // ------------------------------------------------------------------ 6 · parameters
  function paramForm() {
    const P = plan(), p = P.params;
    $("pCp").value = String(P.cpStep); $("pSmooth").value = p.smoothing; $("pIt1").value = p.iters1; $("pIt2").value = p.iters2;
    $("pVseg").value = p.vmatSegs; $("pVlev").value = p.vmatLevels; $("pLev").value = p.levels; $("pMaxSeg").value = p.maxSegs;
    $("pMinA").value = p.minArea; $("pMinMU").value = p.minMU; $("pLeaf").value = p.leafSpeed; $("pGan").value = p.gantrySpeed;
    $("pGrid").value = ENG.state.grid ? ENG.state.grid.h : (p.grid || CASE.ph.grid);
  }
  function applyParams() {
    const P = plan(), p = P.params, oldCp = P.cpStep, oldGrid = ENG.state.grid.h;
    P.cpStep = +$("pCp").value; p.smoothing = $("pSmooth").value; p.iters1 = +$("pIt1").value; p.iters2 = +$("pIt2").value;
    p.vmatSegs = +$("pVseg").value; p.vmatLevels = +$("pVlev").value; p.levels = +$("pLev").value; p.maxSegs = +$("pMaxSeg").value;
    p.minArea = +$("pMinA").value; p.minMU = +$("pMinMU").value; p.leafSpeed = +$("pLeaf").value; p.gantrySpeed = +$("pGan").value;
    const g = Math.max(0.3, Math.min(2, +$("pGrid").value)); p.grid = g;
    if (oldCp !== P.cpStep || Math.abs(g - oldGrid) > 1e-6) rebuild("Rebuilding with new parameters…"); else { optStatus(); evalTables(); }
  }

  // ------------------------------------------------------------------ 7 · optimisation
  function optButtons(dis) { for (const id of ["btnS1", "btnS2", "btnCalc", "btnW", "btnFinal"]) $(id).disabled = dis; }
  function progress(i, n, obj, label) {
    $("busyText").textContent = `${label} · iteration ${i}/${n}${obj !== undefined ? ` · cost ${obj.toFixed(4)}` : ""}`;
    $("optProgress").firstElementChild.style.width = `${100 * i / n}%`;
    if (i % 10 === 0) drawObjPlot();
  }
  function done(err) {
    optButtons(false); busy(false);
    if (err) { $("optStatus").innerHTML = `<span class="bad">${esc(err)}</span>`; return; }
    invalidate(); drawObjPlot(); optStatus(); evalTables(); beamList(); setCP(S.cpIndex);
    req(...ALL);
  }
  function stage1() {
    play(false); optButtons(true); const P = plan(), n = P.params.iters1;
    busy(true, "Stage 1 · fluence optimisation…");
    ENG.optimise(n, { part: +$("optPart").value }, (i, N, o) => progress(i, N, o, "Stage 1 · fluence"), done);
  }
  function stage2() {
    play(false); optButtons(true); const P = plan();
    busy(true, "Stage 2 · MLC segmentation and segment weights…");
    ENG.stage2(P.params.iters2, { part: +$("optPart").value }, (i, N, o) => progress(i, N, o, "Stage 2 · segments"), done);
  }
  function calc() { play(false); busy(true, "Calculating dose…"); later(() => { ENG.calculate(); afterSetup(); done(); }); }
  function weights() {
    play(false); optButtons(true); busy(true, "Optimising beam weights…");
    ENG.optimiseWeights(Math.max(40, Math.round(plan().params.iters1 / 3)), (i, N, o) => progress(i, N, o, "Beam weights"), () => { beamEditor(); done(); });
  }
  function finalDose() {
    play(false); optButtons(true); busy(true, "Final calculation on the fine grid…");
    ENG.finalCalc((v, n) => { $("busyText").textContent = `Final calculation on a ${(ENG.state.grid.h / 2).toFixed(2)} cm grid… ${Math.round(100 * v / n)}%`; }, () => done());
  }
  function optStatus() {
    const st = ENG.state, P = plan(), stage = ["not optimised (initial fluence)", "Stage 1 (ideal fluence)", "Stage 2 (deliverable segments)", "forward calculated"][st.stage] || "";
    $("optStatus").innerHTML = `Plan state: <b>${stage}</b>${st.fine ? " · fine-grid dose available" : ""}${st.stage === 2 && st.leafPerDeg ? ` · largest leaf move ≈ ${st.leafPerDeg.toFixed(2)} cm/°` : ""}`;
    const rows = P.objectives.filter(o => o.on).map(o => `<tr><td>${esc(o.struct)}</td><td>${o.type}${o.mode === "constraint" ? " (con)" : ""}</td><td class="num">${o._ach || "–"}</td><td class="num">${o._f !== undefined ? o._f.toFixed(4) : "–"}</td></tr>`);
    $("objStatus").innerHTML = `<tr><th>Structure</th><th>Cost function</th><th style="text-align:right">Achieved</th><th style="text-align:right">Cost</th></tr>` + rows.join("");
    const P2 = P.beams.some(b => (b.part || 1) === 2); $("optPart").disabled = !P2; if (!P2) $("optPart").value = "0";
    const opt = P.beams.some(b => !b.off && (b.mlc || "optimised") === "optimised");
    $("btnS1").disabled = !opt; $("btnS2").disabled = !opt; $("btnW").disabled = opt;
  }
  function drawObjPlot() {
    const cv = $("objPlot"), dpr = devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
    if (!W) return;
    cv.width = W * dpr; cv.height = H * dpr; const g = cv.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.fillStyle = "#0b0f14"; g.fillRect(0, 0, W, H);
    const h = ENG.state.history; if (h.length < 2) return;
    const mx = Math.max(...h.slice(1)), mn = Math.max(1e-9, Math.min(...h));
    g.strokeStyle = "#8b5cf6"; g.lineWidth = 1.5; g.beginPath();
    h.forEach((v, i) => { const x = 6 + (W - 12) * i / (h.length - 1), y = H - 8 - (H - 22) * (Math.log(v + 1e-9) - Math.log(mn)) / Math.max(1e-6, Math.log(mx + 1e-9) - Math.log(mn)); i ? g.lineTo(x, y) : g.moveTo(x, y); });
    g.stroke(); g.fillStyle = "#8394a7"; g.font = "11px system-ui"; g.fillText(`total cost (log) · ${h.length} iterations · ${h[h.length - 1].toFixed(4)}`, 8, 13);
  }

  // ------------------------------------------------------------------ 8 · evaluation
  function fmtGoal(g) {
    const m = g.metric === "V" ? `V${g.x} Gy (%)` : g.metric === "D" ? `D${g.x}% (Gy)` : g.metric === "MU" ? "MU / fraction" : `${g.metric}${["HI", "CI"].includes(g.metric) ? "" : " (Gy)"}`;
    return `${g.metric === "MU" ? "" : esc(g.struct) + " "}${m}${g.op ? ` ${g.op} ${g.limit}` : ""}`;
  }
  function evalTables() {
    const st = stats(), P = plan(), snaps = compareSnaps();
    $("gridInfo").textContent = `(dose grid ${st.grid} cm${ENG.state.fine ? ", fine" : ""})`;
    const goals = P.goals || [], hasLit = goals.some(g => g.lit !== null && g.lit !== undefined);
    const f = v => v === null || v === undefined ? "–" : Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2);
    const head = `<tr><th>Goal</th><th style="text-align:right">Plan</th>${snaps.map(s => `<th style="text-align:right" title="${esc(s.name)}">${esc(s.name.slice(0, 8))}</th>`).join("")}${hasLit ? '<th style="text-align:right">Lit.</th>' : ""}</tr>`;
    $("goalTable").innerHTML = head + goals.map(g => {
      const v = ENG.goalValue(st, g), ok = v === null || !g.op ? "" : (g.op === "<=" ? v <= g.limit : v >= g.limit) ? "good" : "bad";
      return `<tr><td>${fmtGoal(g)}</td><td class="num ${ok}">${f(v)}</td>${snaps.map(s => `<td class="ref">${f(ENG.goalValue(s.stats, g))}</td>`).join("")}${hasLit ? `<td class="lit">${g.lit ?? ""}</td>` : ""}</tr>`;
    }).join("");
    const rx = P.rx, rows = [["V95% (%)", st.V95], ["V100% (%)", st.V100], ["V107% (%)", st.V107], ["D98% (Gy)", st.D98], ["D95% (Gy)", st.D95], ["D50% (Gy)", st.D50], ["D2% (Gy)", st.D2],
      ["Dmean (Gy)", st.Dmean], ["HI = (D2−D98)/D50", st.HI], ["Paddick CI (95 %)", st.CI], ["Body Dmax (Gy)", st.Dmax]];
    $("statsTable").innerHTML = `<tr><th>${esc(P.target)} (Rx ${rx} Gy)</th><th style="text-align:right">Plan</th>${snaps.map(s => `<th style="text-align:right">${esc(s.name.slice(0, 8))}</th>`).join("")}</tr>` +
      rows.map(([n, v]) => `<tr><td>${n}</td><td class="num">${f(v)}</td>${snaps.map(s => `<td class="ref">${f(s.stats[{ "V95% (%)": "V95", "V100% (%)": "V100", "V107% (%)": "V107", "D98% (Gy)": "D98", "D95% (Gy)": "D95", "D50% (Gy)": "D50", "D2% (Gy)": "D2", "Dmean (Gy)": "Dmean", "HI = (D2−D98)/D50": "HI", "Paddick CI (95 %)": "CI", "Body Dmax (Gy)": "Dmax" }[n]])}</td>`).join("")}</tr>`).join("");
    const mu = st.mu;
    $("muTable").innerHTML = `<tr><th>Beam</th><th style="text-align:right">MU/fx</th><th style="text-align:right">Segs</th><th style="text-align:right">min</th></tr>` +
      Object.entries(mu.perBeam).map(([i, r]) => `<tr><td>${esc(P.beams[i].name)}</td><td class="num">${r.mu.toFixed(0)}</td><td class="num">${r.segs}</td><td class="num">${(r.time / 60).toFixed(1)}</td></tr>`).join("") +
      `<tr><td><b>Total</b>${mu.estimated ? " (estimate from fluence)" : ""}</td><td class="num"><b>${mu.total.toFixed(0)}</b></td><td></td><td class="num">${mu.minutes.toFixed(1)}</td></tr>`;
    $("evalNote").textContent = `MU: ${ENG.state.stage < 2 ? "before Stage 2 the MU are estimated from the peak fluence" : "sum of segment weights"}; beam-on time assumes ${P.params.maxDoseRate} MU/min and ${P.params.gantrySpeed}°/s. Training values only.`;
    pointTable();
  }
  function snapshot(name, grid, dose, stObj) {
    const id = ++snapId, s = { id, name, grid, dose, stats: stObj || ENG.stats({ grid, dose }), profAxis: S.profAxis };
    const keepSrc = S.doseSrc; S.doseSrc = { kind: "snap", a: id }; S.snapshots.push(s);
    s.profile = V2.profileData(S, S.profAxis); S.doseSrc = keepSrc;
    S.compare.add(id); if (S.compare.size > 4) S.compare.delete([...S.compare][0]);
    snapList(); evalTables(); req("dvh");
    return s;
  }
  function takeSnapshot() {
    const P = plan(), g = ENG.state.fine || ENG.state.grid, n = `${P.name.split(",")[0].slice(0, 14)} #${snapId + 1}`;
    const name = prompt("Snapshot name", n); if (name === null) return;
    snapshot(name || n, g, Float32Array.from(g.dose), stats());
  }
  function snapList() {
    const el = $("snapList"); el.innerHTML = S.snapshots.length ? "" : `<div>No snapshots yet — use ★ Snapshot to keep a plan for comparison.</div>`;
    S.snapshots.forEach(s => {
      const d = document.createElement("div");
      d.innerHTML = `<label><input type="checkbox" ${S.compare.has(s.id) ? "checked" : ""}> ${esc(s.name)}</label><span>V95 ${s.stats.V95 !== undefined ? s.stats.V95.toFixed(1) : "–"} % <button data-x title="Delete">✕</button></span>`;
      d.querySelector("input").onchange = e => { e.target.checked ? S.compare.add(s.id) : S.compare.delete(s.id); evalTables(); req("dvh"); };
      d.querySelector("[data-x]").onclick = ev => { ev.stopPropagation(); S.snapshots = S.snapshots.filter(q => q !== s); S.compare.delete(s.id); if (S.doseSrc.a === s.id || S.doseSrc.b === s.id) S.doseSrc = { kind: "plan" }; snapList(); evalTables(); req(...ALL); };
      el.appendChild(d);
    });
    const opts = [`<option value='{"kind":"plan"}'>Current plan</option>`];
    for (const s of S.snapshots) {
      opts.push(`<option value='{"kind":"snap","a":${s.id}}'>Snapshot: ${esc(s.name)}</option>`);
      opts.push(`<option value='{"kind":"diff","a":${s.id}}'>Difference: current − ${esc(s.name)}</option>`);
    }
    for (let i = 0; i < S.snapshots.length; i++) for (let j = i + 1; j < S.snapshots.length; j++)
      if (S.snapshots[i].grid.key === S.snapshots[j].grid.key || true) opts.push(`<option value='{"kind":"sum","a":${S.snapshots[i].id},"b":${S.snapshots[j].id}}'>Plan sum: ${esc(S.snapshots[i].name)} + ${esc(S.snapshots[j].name)}</option>`);
    $("doseSrc").innerHTML = opts.join(""); $("doseSrc").value = JSON.stringify(S.doseSrc);
    if ($("doseSrc").selectedIndex < 0) { S.doseSrc = { kind: "plan" }; $("doseSrc").selectedIndex = 0; }
  }
  function pointTable() {
    const snaps = compareSnaps();
    $("pointTable").innerHTML = S.points.length ? `<tr><th>Point</th><th>x, y, z</th><th style="text-align:right">Plan (Gy)</th>${snaps.map(s => `<th style="text-align:right">${esc(s.name.slice(0, 8))}</th>`).join("")}</tr>` +
      S.points.map(p => `<tr><td>${esc(p.name)}</td><td>${p.x.toFixed(1)}, ${p.y.toFixed(1)}, ${p.z.toFixed(1)}</td><td class="num">${ENG.doseAt(p.x, p.y, p.z).toFixed(2)}</td>${snaps.map(s => `<td class="ref">${ENG.sampleGrid(s.grid, s.dose, p.x, p.y, p.z).toFixed(2)}</td>`).join("")}</tr>`).join("") : "";
  }
  function addPoint(x, y, z) { S.points.push({ name: `P${S.points.length + 1}`, x, y, z }); pointTable(); req("ax", "cor", "sag"); }
  function shiftOptions() {
    const G = V2.isoGroups(plan());
    $("shWhich").innerHTML = `<option value="all">all beams (patient set-up error)</option>` + G.map((g, i) => `<option value="${i}">isocentre ${esc(g.label)} only (${g.orient}, z ${g.iso.z})</option>`).join("");
  }
  function runShift(sign, cb) {
    const sh = { x: sign * +$("shX").value, y: sign * +$("shY").value, z: sign * +$("shZ").value }, w = $("shWhich").value;
    const G = V2.isoGroups(plan()), filt = w === "all" ? null : (bi => G[+w].beams.includes(bi));
    const lab = `${w === "all" ? "all" : G[+w].label} shift ${sh.x}/${sh.y}/${sh.z}`;
    busy(true, `Recalculating with ${lab} cm…`);
    ENG.robust(sh, filt, (v, n) => { $("busyText").textContent = `Recalculating with ${lab} cm… ${Math.round(100 * v / n)}%`; }, dose => {
      busy(false); snapshot(lab, ENG.state.grid, dose); cb && cb();
    });
  }

  // ------------------------------------------------------------------ 9 · display
  function isoChecks() {
    const ic = $("isoChecks"); ic.innerHTML = "";
    V2.ISO_LEVELS.forEach(L => {
      const l = document.createElement("label");
      l.innerHTML = `<input type="checkbox" ${S.isoLevels[L.p] ? "checked" : ""}> <span class="sw" style="background:${L.c}"></span>${L.p}% (${(plan().rx * L.p / 100).toFixed(1)} Gy)`;
      l.querySelector("input").onchange = e => { S.isoLevels[L.p] = e.target.checked; req("ax", "cor", "sag"); }; ic.appendChild(l);
    });
  }

  // ------------------------------------------------------------------ save / open / screenshot
  function savePlan() {
    const withF = confirm("Include the optimised fluence and segments?\nOK = parameters + fluence (larger file), Cancel = parameters only");
    const obj = ENG.exportPlan(withF), blob = new Blob([JSON.stringify(obj)], { type: "application/json" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `${plan().name.replace(/[^\w-]+/g, "_")}.plan.json`; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }
  function openPlan(file) {
    const rd = new FileReader();
    rd.onload = () => {
      let obj; try { obj = JSON.parse(rd.result); } catch (e) { alert("Not a valid JSON file"); return; }
      if (obj.format !== "rt-planning-simulator-plan" || !PHANTOMS.byId[obj.phantom]) { alert("This is not a plan file of this simulator."); return; }
      busy(true, "Opening plan…");
      later(() => {
        try {
          if (!CASE.ph || CASE.ph.id !== obj.phantom) { CASE.load(obj.phantom); S.snapshots = []; S.compare.clear(); S.points = []; S.doseSrc = { kind: "plan" }; ROOM.buildPatient(); const c = CASE.ph.cross; S.cross = { ...c }; }
          if (obj.structures) CASE.importStructs(obj.structures);
          obj.plan.params = Object.assign({}, PLANS.P0, obj.plan.params || {});
          ENG.setup(obj.plan);
          if (obj.fluence && !ENG.importFluence(obj)) alert("The fluence in the file does not match the beams; parameters only were loaded.");
          $("phantom").value = obj.phantom; fillPresets(obj.phantom);
        } catch (e) { console.error(e); alert("Could not open the plan: " + e.message); }
        busy(false); invalidate(); refreshAll(); setCP(0);
      });
    };
    rd.readAsText(file);
  }
  function screenshot() {
    flush();
    const ids = ["vRoom", "vBEV", "vDVH", "vAx", "vCor", "vSag"].filter(id => $(id).offsetParent !== null);
    const r0 = $("views").getBoundingClientRect(), dpr = devicePixelRatio || 1;
    const out = document.createElement("canvas"); out.width = r0.width * dpr; out.height = (r0.height + 40) * dpr;
    const g = out.getContext("2d"); g.scale(dpr, dpr); g.fillStyle = "#070a0e"; g.fillRect(0, 0, r0.width, r0.height + 40);
    for (const id of ids) {
      const v = $(id), cv = [...v.querySelectorAll("canvas")].find(c => c.style.display !== "none"), r = cv.getBoundingClientRect();
      g.drawImage(cv, r.left - r0.left, r.top - r0.top, r.width, r.height);
      if (id === "vRoom") {
        g.fillStyle = "#e8eef5"; g.font = "600 12px system-ui"; g.fillText("Room view", r.left - r0.left + 8, r.top - r0.top + 16);
        g.font = "11px system-ui"; g.textAlign = "right"; $("roomInfo").innerText.split("\n").forEach((t, i) => g.fillText(t, r.right - r0.left - 8, r.top - r0.top + 16 + 14 * i)); g.textAlign = "left";
      }
    }
    g.fillStyle = "#9fb3c8"; g.font = "12px system-ui";
    g.fillText(`RT Planning Simulator (educational) · ${CASE.ph.name} · ${plan().name} · approximate dose model · not a clinical TPS`, 10, r0.height + 25);
    const a = document.createElement("a"); a.download = `RT_simulator_${Date.now()}.png`; a.href = out.toDataURL("image/png"); a.click();
  }

  // ------------------------------------------------------------------ events
  document.querySelectorAll(".steps button").forEach(b => b.onclick = () => {
    document.querySelectorAll(".steps button").forEach(x => x.classList.toggle("on", x === b));
    document.querySelectorAll(".tab").forEach(t => t.classList.toggle("on", t.id === "tab-" + b.dataset.tab));
    if (b.dataset.tab === "opt") { drawObjPlot(); optStatus(); }
    if (b.dataset.tab === "eval") evalTables();
  });
  document.querySelectorAll(".vtabs button").forEach(b => b.onclick = () => {
    document.querySelectorAll(".vtabs button").forEach(x => x.classList.toggle("on", x === b));
    S.panel = b.dataset.p; $("cDVH").style.display = S.panel === "dvh" ? "" : "none"; $("cProf").style.display = S.panel === "prof" ? "" : "none"; req("dvh");
  });
  $("quickPreset").onchange = e => loadTemplate(e.target.value);
  $("phantom").onchange = e => fillPresets(e.target.value);
  $("loadPreset").onclick = () => loadTemplate($("preset").value);
  $("btnPlay").onclick = () => play(!S.playing); $("btnSnap").onclick = takeSnapshot; $("btnShot").onclick = screenshot;
  $("btnSave").onclick = savePlan; $("btnOpen").onclick = () => $("fileOpen").click();
  $("fileOpen").onchange = e => { if (e.target.files[0]) openPlan(e.target.files[0]); e.target.value = ""; };
  $("layout").onchange = e => { $("views").className = e.target.value; setTimeout(() => req(...ALL), 50); };
  // structures
  $("layering").onchange = markDirty; $("applyStruct").onclick = applyStructures;
  $("btnNew").onclick = () => {
    const n = $("newName").value.trim().replace(/\s+/g, "_"); if (!n) return;
    try { CASE.newStruct(n, $("newRole").value); $("newName").value = ""; S.editStruct = n; structTable(); $("editStruct").value = n; contourMsg(`Created ${n}. Paint it with the brush, or fill it with a margin / Boolean operation.`); markDirty(); }
    catch (e) { contourMsg(e.message); }
  };
  $("editStruct").onchange = e => { S.editStruct = e.target.value; req("ax", "cor", "sag"); };
  $("tool").onchange = e => { S.tool = e.target.value; if (S.tool && !S.editStruct) contourMsg("Choose the structure to edit first."); };
  const needEdit = () => { if (!S.editStruct) { contourMsg("Choose the structure to edit (Edit)."); return false; } return true; };
  const afterEdit = msg => { contourMsg(msg); structTable(); markDirty(); bev.cache = {}; req("ax", "cor", "sag", "bev", "room"); };
  $("btnMargin").onclick = () => { if (!needEdit()) return; busy(true, "Margin…"); later(() => { CASE.margin($("mSrc").value, S.editStruct, +$("mCm").value); busy(false); afterEdit(`${S.editStruct} = ${$("mSrc").value} ${+$("mCm").value >= 0 ? "+" : ""}${$("mCm").value} cm`); }); };
  $("btnBool").onclick = () => { if (!needEdit()) return; CASE.boolean($("bA").value, $("bOp").value, $("bB").value, S.editStruct); afterEdit(`${S.editStruct} = ${$("bA").value} ${$("bOp").selectedOptions[0].text} ${$("bB").value}`); };
  $("btnInterp").onclick = () => { if (!needEdit()) return; const n = CASE.interpolate(S.editStruct); afterEdit(`Interpolated ${n} voxels between contoured slices of ${S.editStruct}.`); };
  $("btnClear").onclick = () => { if (!needEdit()) return; CASE.clearStruct(S.editStruct); afterEdit(`${S.editStruct} cleared.`); };
  $("btnDelStruct").onclick = () => {
    if (!needEdit()) return; const n = S.editStruct;
    if (plan().objectives.some(o => o.struct === n) && !confirm(`${n} is used by cost functions. Delete anyway?`)) return;
    CASE.removeStruct(n); plan().objectives = plan().objectives.filter(o => o.struct !== n); S.editStruct = ""; objTable(); afterEdit(`${n} deleted.`);
  };
  // beams
  $("addArc").onclick = () => addBeam("arc"); $("addStatic").onclick = () => addBeam("static"); $("addIso").onclick = addIso;
  $("dupBeam").onclick = () => { const P = plan(), b = P.beams[S.selBeam]; if (!b) return; const c = JSON.parse(JSON.stringify(b)); c.name += "b"; P.beams.splice(S.selBeam + 1, 0, c); S.selBeam++; beamList(); beamEditor(); };
  $("delBeam").onclick = () => { const P = plan(); if (P.beams.length < 2) return; P.beams.splice(S.selBeam, 1); S.selBeam = Math.max(0, S.selBeam - 1); beamList(); beamEditor(); overlapInfo(); };
  $("applyBeams").onclick = () => { $("applyBeams").textContent = "Apply beams"; rebuild("Rebuilding beams and dose influence…"); };
  $("applyRx").onclick = applyRx; $("applyParam").onclick = applyParams;
  $("addObj").onclick = () => { plan().objectives.push(PLANS.ob(plan().target, "Quadratic Overdose", plan().rx * 1.05, 0.5)); objTable(); };
  // optimisation
  $("btnS1").onclick = stage1; $("btnS2").onclick = stage2; $("btnCalc").onclick = calc; $("btnW").onclick = weights; $("btnFinal").onclick = finalDose;
  // evaluation
  $("doseSrc").onchange = e => { S.doseSrc = JSON.parse(e.target.value); S.doseVersion++; req("ax", "cor", "sag", "dvh"); };
  $("addPoint").onclick = () => addPoint(S.cross.x, S.cross.y, S.cross.z);
  $("clrPoints").onclick = () => { S.points = []; pointTable(); req("ax", "cor", "sag"); };
  $("btnShift").onclick = () => runShift(1);
  $("btnShiftPM").onclick = () => runShift(1, () => runShift(-1));
  // display
  $("doseMode").onchange = e => { S.doseMode = e.target.value; req("ax", "cor", "sag"); };
  $("win").onchange = e => { const [c, w] = e.target.value.split(",").map(Number); S.window = { c, w }; req("ax", "cor", "sag"); };
  $("profAxis").onchange = e => { S.profAxis = e.target.value; req("dvh"); };
  const ro = { optTransp: "transparent", optTracks: "showTracks", optBeam: "showBeam", optLasers: "showLasers" };
  for (const id in ro) $(id).onchange = e => { ROOM.opts[ro[id]] = e.target.checked; req("room"); };
  $("optMLC").onchange = e => { S.showMLC = e.target.checked; req("bev"); };
  $("optBeams2d").onchange = e => { S.showBeams = e.target.checked; req("ax", "cor", "sag"); };
  document.querySelectorAll("[data-cam]").forEach(b => b.onclick = () => { ROOM.resetView(b.dataset.cam, plan().beams.some(q => q.standing)); req("room"); });
  // timeline
  $("cpSlider").oninput = e => setCP(+e.target.value);
  $("segSlider").oninput = e => { S.segIndex = +e.target.value; req("bev"); };
  $("prevCP").onclick = () => setCP(S.cpIndex - 1); $("nextCP").onclick = () => setCP(S.cpIndex + 1);
  window.addEventListener("keydown", e => {
    if (["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName)) return;
    if (e.key === "ArrowRight") setCP(S.cpIndex + 1);
    if (e.key === "ArrowLeft") setCP(S.cpIndex - 1);
    if (e.key === " ") { play(!S.playing); e.preventDefault(); }
  });
  // slice interaction: wheel = slice, click = crosshair, Shift+click = point dose, brush when a tool is active
  const bind = v => {
    const sg = () => CASE.sg;
    const world = e => { const m = v._m, r = v.cv.getBoundingClientRect(); return { u: m.U(e.clientX - r.left), w: m.V(e.clientY - r.top), px: e.clientX - r.left, py: e.clientY - r.top }; };
    const toXYZ = ({ u, w }) => v.kind === "axial" ? [u, w, S.cross.z] : v.kind === "coronal" ? [u, S.cross.y, w] : [S.cross.x, u, w];
    let painting = false;
    const paint = e => {
      const p = world(e), [x, y, z] = toXYZ(p);
      CASE.brush(S.editStruct, v.kind, x, y, z, +$("brushR").value, S.tool === "erase");
      S.brush = { view: v.kind, px: p.px, py: p.py, r: +$("brushR").value, erase: S.tool === "erase" };
      req(v.kind === "axial" ? "ax" : v.kind === "coronal" ? "cor" : "sag");
    };
    v.cv.addEventListener("wheel", e => {
      e.preventDefault(); const d = Math.sign(e.deltaY) * (e.shiftKey ? 2.5 : 0.5), G = sg();
      if (v.kind === "axial") S.cross.z = Math.max(G.z0 + 0.25, Math.min(G.z0 + G.nz * G.h - 0.25, S.cross.z + d));
      else if (v.kind === "coronal") S.cross.y = Math.max(G.y0, Math.min(G.y0 + G.ny * G.h, S.cross.y + d));
      else S.cross.x = Math.max(G.x0, Math.min(G.x0 + G.nx * G.h, S.cross.x + d));
      req("ax", "cor", "sag", ...(S.panel === "prof" ? ["dvh"] : []));
    }, { passive: false });
    v.cv.addEventListener("mousedown", e => {
      if (!v._m) return;
      if (S.tool && S.editStruct) { painting = true; paint(e); e.preventDefault(); return; }
      const [x, y, z] = toXYZ(world(e));
      if (e.shiftKey) { addPoint(x, y, z); return; }
      const G = sg(); S.cross = { x: Math.max(G.x0, Math.min(G.x0 + G.nx * G.h, x)), y: Math.max(G.y0, Math.min(G.y0 + G.ny * G.h, y)), z: Math.max(G.z0 + 0.25, Math.min(G.z0 + G.nz * G.h - 0.25, z)) };
      req("ax", "cor", "sag", ...(S.panel === "prof" ? ["dvh"] : []));
    });
    v.cv.addEventListener("mousemove", e => {
      if (!v._m) return;
      if (painting) paint(e);
      else if (S.tool && S.editStruct) { const p = world(e); S.brush = { view: v.kind, px: p.px, py: p.py, r: +$("brushR").value, erase: S.tool === "erase" }; req(v.kind === "axial" ? "ax" : v.kind === "coronal" ? "cor" : "sag"); }
    });
    window.addEventListener("mouseup", () => { if (painting) { painting = false; structTable(); markDirty(); bev.cache = {}; req("ax", "cor", "sag", "bev"); } });
    v.cv.addEventListener("mouseleave", () => { if (S.brush && S.brush.view === v.kind) { S.brush = null; req(v.kind === "axial" ? "ax" : v.kind === "coronal" ? "cor" : "sag"); } });
  };
  bind(views.ax); bind(views.cor); bind(views.sag);
  window.addEventListener("resize", () => req(...ALL));
  ROOM.onChange = () => req("room");

  // ------------------------------------------------------------------ start
  fillPhantoms();
  if (!ROOM.init($("cRoom"))) $("roomInfo").innerHTML = "<b>WebGL is not available in this browser</b>";
  const start = (location.hash.match(/preset=([\w-]+)/) || [])[1] || "tbi-thesis";
  loadTemplate(PLANS.byId[start] ? start : "tbi-thesis");
  window.SIM = { S, req, stage1, stage2, calc, finalDose, setCP, play, loadTemplate, ENG, CASE, snapshot, runShift, evalTables, flush };
})();
