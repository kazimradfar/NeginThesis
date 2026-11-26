/* TBI Planning Simulator — user interface and interaction. */
"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const S = {
    cross: { x: 0, y: 0.8, z: 42.5 }, window: { c: 40, w: 400 }, doseMode: "iso",
    isoLevels: { 110: 1, 105: 1, 100: 1, 95: 1, 90: 1, 80: 1, 50: 1 },
    showStruct: { Body: true, PTV: true, Lung_R: true, Lung_L: true, Lungs: true, Kidneys: true },
    showBeams: true, showMLC: true, cpIndex: 0, cp: null, doseVersion: 0, playing: false, shift: 42.5, theta: 180, panel: "dvh",
  };
  const views = { ax: new V2.SliceView($("cAx"), "axial"), cor: new V2.SliceView($("cCor"), "coronal"), sag: new V2.SliceView($("cSag"), "sagittal") };
  const bev = new V2.BEV($("cBEV"));
  const LIT = { V90: 98.8, V95: 96.5, D98: 11.0, D50: 12.0, D2: 12.8, HI: 0.15, lungMean: 8.8, lungV12: 4.5, Dmax: 14.2, MU: 3581, beamOn: 15.1 };

  // ------------------------------------------------------------------ busy overlay
  function busy(on, text) { $("busy").classList.toggle("on", !!on); if (text) $("busyText").textContent = text; }

  // ------------------------------------------------------------------ render loop
  let pending = new Set(), raf = 0;
  function req(...what) { what.forEach(w => pending.add(w)); if (!raf) raf = requestAnimationFrame(flush); }
  function flush() {
    raf = 0; const p = pending; pending = new Set();
    if (p.has("room")) renderRoom();
    if (p.has("bev")) bev.draw(S);
    if (p.has("ax")) views.ax.draw(S);
    if (p.has("cor")) views.cor.draw(S);
    if (p.has("sag")) views.sag.draw(S);
    if (p.has("dvh")) renderPanel();
  }
  const ALL = ["room", "bev", "ax", "cor", "sag", "dvh"];
  function renderRoom() {
    const cp = S.cp, plan = ENG.state.plan;
    let prog = 0;
    if (cp) { const n = Math.round(360 / plan.cpStep); prog = (cp.k + 1) / n; }
    ROOM.render({ theta: S.theta, shift: S.shift, cp, plan, isoIdx: cp ? cp.iso : 0, progress: prog, arcDir: cp ? cp.dir : 1 });
    if (cp) {
      const iso = plan.isos[cp.iso];
      $("roomInfo").innerHTML = `Gantry <b>${S.theta.toFixed(1)}°</b> · Collimator <b>90°</b> · Couch <b>0°</b><br>` +
        `Couch longitudinal <b>${S.shift.toFixed(1)} cm</b> (iso ${iso.name})<br>Arc ${cp.arc + 1} ${cp.dir > 0 ? "CW" : "CCW"} · CP ${cp.k + 1}/${Math.round(360 / plan.cpStep)}`;
    }
  }
  let statsCache = null, refStats = null;
  function stats() { if (!statsCache) statsCache = ENG.stats(); return statsCache; }
  function renderPanel() {
    if (S.panel === "dvh") V2.drawDVH($("cDVH"), stats(), S, refStats); else V2.drawProfile($("cProf"), S, refProfile);
  }

  // ------------------------------------------------------------------ control points
  function setCP(i, animateCouch) {
    const cps = ENG.state.cps; if (!cps.length) return;
    S.cpIndex = Math.max(0, Math.min(cps.length - 1, i));
    S.cp = cps[S.cpIndex]; S.theta = S.cp.theta;
    const target = ENG.state.plan.isos[S.cp.iso].z;
    if (animateCouch && Math.abs(target - S.shift) > 0.05) moveCouch(target); else S.shift = target;
    $("cpSlider").value = S.cpIndex;
    const plan = ENG.state.plan, iso = plan.isos[S.cp.iso], lv = ENG.leaves(S.cp);
    const mu = lv.max * ENG.state.scale * 100 / plan.fx;
    $("cpInfo").textContent = `CP ${S.cpIndex + 1}/${cps.length} · Iso ${iso.name} (z ${iso.z.toFixed(1)} cm) · Arc ${S.cp.arc + 1} ${S.cp.dir > 0 ? "CW" : "CCW"} · Gantry ${S.cp.theta.toFixed(1)}° · ≈${mu.toFixed(1)} MU at this CP`;
    if (Math.abs(S.cross.z - iso.z) > (iso.hi - iso.lo) / 2 + 1 && !S.playing) { /* keep user's slice */ }
    req("room", "bev", "ax");
  }
  let couchAnim = 0;
  function moveCouch(target) {
    cancelAnimationFrame(couchAnim);
    const start = S.shift, t0 = performance.now(), dur = 900;
    const step = () => {
      const t = Math.min(1, (performance.now() - t0) / dur), e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      S.shift = start + (target - start) * e; req("room");
      if (t < 1) couchAnim = requestAnimationFrame(step);
    };
    couchAnim = requestAnimationFrame(step);
  }
  let playTimer = 0;
  function play(on) {
    S.playing = on; $("btnPlay").textContent = on ? "⏸ Pause" : "▶ Play arcs";
    clearTimeout(playTimer);
    if (!on) return;
    const tick = () => {
      if (!S.playing) return;
      const cps = ENG.state.cps, next = (S.cpIndex + 1) % cps.length;
      const isoChange = cps[next].iso !== S.cp.iso;
      setCP(next, true);
      if (Math.abs(S.cross.z - cps[next].z0) > 1 && isoChange) { S.cross.z = cps[next].z0; req("ax"); }
      playTimer = setTimeout(tick, isoChange ? 1100 : 110);
    };
    tick();
  }

  // ------------------------------------------------------------------ plan editing
  function presetPlan(name) {
    const p = ENG.defaultPlan();
    if (name === "overlap4") { p.isos[0].hi = 16.5; p.isos[1].lo = -14.5; p.isos[1].hi = 14.5; p.isos[2].lo = -19.0; }
    if (name === "lung75") { p.objectives[2].dose = 7.5; }
    if (name === "single") p.isos.forEach(i => i.arcs = 1);
    if (name === "four") {
      p.isos = [{ name: "A", z: 11.5, lo: -11.5, hi: 12.5, arcs: 2 }, { name: "B", z: 34.5, lo: -11.5, hi: 11.5, arcs: 2 },
                { name: "C", z: 56.5, lo: -11.5, hi: 11.5, arcs: 2 }, { name: "D", z: 78.5, lo: -11.5, hi: 11.5, arcs: 2 }];
    }
    return p;
  }
  function isoTable() {
    const tb = $("isoTable").tBodies[0]; tb.innerHTML = "";
    ENG.state.plan.isos.forEach((iso, i) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td><span class="sw" style="background:${V2.ISO_COL[i % 5]};display:inline-block;width:9px;height:9px;border-radius:2px"></span> ${iso.name}</td>
        <td><input type="number" step="0.5" value="${iso.z}" data-k="z"></td><td><input type="number" step="0.5" value="${iso.lo}" data-k="lo"></td>
        <td><input type="number" step="0.5" value="${iso.hi}" data-k="hi"></td>
        <td><select data-k="arcs"><option ${iso.arcs === 1 ? "selected" : ""}>1</option><option ${iso.arcs === 2 ? "selected" : ""}>2</option></select></td>
        <td><button data-del="${i}" title="Remove">✕</button></td>`;
      tr.querySelectorAll("[data-k]").forEach(el => el.addEventListener("change", () => {
        const k = el.dataset.k; iso[k] = k === "arcs" ? +el.value : +el.value; overlapInfo(); req("cor", "sag");
      }));
      tr.querySelector("[data-del]").onclick = () => { if (ENG.state.plan.isos.length > 1) { ENG.state.plan.isos.splice(i, 1); isoTable(); overlapInfo(); req("cor", "sag"); } };
      tb.appendChild(tr);
    });
    overlapInfo();
  }
  function overlapInfo() {
    const I = ENG.state.plan.isos.slice().sort((a, b) => a.z - b.z), out = [];
    for (const iso of I) {
      const len = iso.hi - iso.lo;
      if (len > 40) out.push(`<span class="bad">Iso ${iso.name}: field length ${len.toFixed(1)} cm exceeds 40 cm</span>`);
    }
    for (let i = 0; i < I.length - 1; i++) {
      const ov = I[i].z + I[i].hi - (I[i + 1].z + I[i + 1].lo);
      out.push(ov >= 0 ? `Overlap ${I[i].name}–${I[i + 1].name}: <b>${ov.toFixed(1)} cm</b>, isocentre distance ${(I[i + 1].z - I[i].z).toFixed(1)} cm`
                       : `<span class="bad">GAP ${I[i].name}–${I[i + 1].name}: ${(-ov).toFixed(1)} cm (cold band!)</span>`);
    }
    const top = I[0].z + I[0].lo, bot = I[I.length - 1].z + I[I.length - 1].hi;
    if (top > 0.5) out.push(`<span class="bad">Vertex not covered (fields start at z = ${top.toFixed(1)} cm)</span>`);
    if (bot < PH.LENGTH - 0.5) out.push(`<span class="bad">Feet end not covered (fields end at z = ${bot.toFixed(1)} cm)</span>`);
    $("overlapInfo").innerHTML = out.join("<br>");
  }
  function beamList() {
    const st = stats(), plan = ENG.state.plan, el = $("beamList"); el.innerHTML = "";
    plan.isos.forEach(iso => {
      for (let a = 0; a < iso.arcs; a++) {
        const key = iso.name + (a + 1), mu = st.muArc[key] || 0;
        const d = document.createElement("div");
        d.innerHTML = `<span>${iso.name}${a + 1} · ${a % 2 === 0 ? "CW 181→179°" : "CCW 179→181°"} · Y ${iso.lo}/${iso.hi}</span><span>≈${mu.toFixed(0)} MU</span>`;
        el.appendChild(d);
      }
    });
  }
  const STRUCT_OPTS = ["PTV", "Lungs", "Lung_R", "Lung_L", "Kidneys", "Body"];
  const TYPE_OPTS = ["Target Penalty", "Quadratic Overdose", "Parallel", "Maximum Dose"];
  function objTable() {
    const tb = $("objTable").tBodies[0]; tb.innerHTML = "";
    ENG.state.plan.objectives.forEach(ob => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td><input type="checkbox" ${ob.on ? "checked" : ""} data-k="on"></td>
        <td><select data-k="struct">${STRUCT_OPTS.map(s => `<option ${s === ob.struct ? "selected" : ""}>${s}</option>`).join("")}</select></td>
        <td><select data-k="type">${TYPE_OPTS.map(s => `<option ${s === ob.type ? "selected" : ""}>${s}</option>`).join("")}</select></td>
        <td><input type="number" step="0.1" value="${ob.dose}" data-k="dose"></td><td><input type="number" step="1" value="${ob.extra}" data-k="extra"></td>
        <td><input type="number" step="0.1" value="${ob.weight}" data-k="weight" style="width:42px"></td>`;
      tr.querySelectorAll("[data-k]").forEach(el => el.addEventListener("change", () => {
        const k = el.dataset.k; ob[k] = k === "on" ? el.checked : (k === "struct" || k === "type") ? el.value : +el.value;
      }));
      tb.appendChild(tr);
    });
  }
  function statsTable() {
    const st = stats(), rx = ENG.state.plan.rx;
    $("gridInfo").textContent = `(DVH grid ${st.grid}${ENG.state.optimised ? ", optimised" : ", open arcs"})`;
    const f = (v, n) => v.toFixed(n);
    const rows = [
      ["PTV V90% (%)", f(st.V90, 1), LIT.V90, st.V90 >= 95], ["PTV V95% (%)", f(st.V95, 1), LIT.V95], ["PTV D98% (Gy)", f(st.D98, 2), LIT.D98, st.D98 >= 0.9 * rx],
      ["PTV D50% (Gy)", f(st.D50, 2), LIT.D50], ["PTV D2% (Gy)", f(st.D2, 2), LIT.D2, st.D2 <= 1.1 * rx], ["PTV Dmean (Gy)", f(st.Dmean, 2), "12.0"],
      ["HI (ICRU 83)", f(st.HI, 3), LIT.HI], ["Lungs Dmean (Gy)", f(st.lungMean, 2), LIT.lungMean, st.lungMean <= 10], ["Lung R / L mean (Gy)", `${f(st.lungR, 2)} / ${f(st.lungL, 2)}`, "8.8 / 8.9"],
      ["Lungs V8 / V10 (%)", `${f(st.lungV8, 0)} / ${f(st.lungV10, 0)}`, "60 / 41"], ["Lungs V12 (%)", f(st.lungV12, 1), LIT.lungV12],
      ["Kidneys Dmean (Gy)", f(st.kidneyMean, 2), "–"], ["Body Dmax (Gy)", f(st.Dmax, 2), LIT.Dmax, st.Dmax <= 1.2 * rx],
      ["MU per fraction (est.)", f(st.MU, 0), LIT.MU], ["Beam-on (min, est.)", f(st.beamOn, 1), LIT.beamOn],
    ];
    const R = refStats ? refRows : null;
    $("statsTable").innerHTML = `<tr><th>Parameter</th><th style="text-align:right">Plan</th>${R ? '<th style="text-align:right">Ref.</th>' : ""}<th style="text-align:right">Thesis</th></tr>` +
      rows.map(([n, v, l, ok], i) => `<tr><td>${n}</td><td class="${ok === undefined ? "" : ok ? "good" : "bad"}">${v}</td>${R ? `<td style="text-align:right;color:#c9a0ff">${R[i][1]}</td>` : ""}<td>${l}</td></tr>`).join("");
    lastRows = rows;
  }
  let lastRows = null, refRows = null, refProfile = null;
  function setReference() {
    refStats = stats(); refRows = lastRows;
    refProfile = V2.profileData(S);
    $("btnRef").textContent = "★ Reference set"; statsTable(); req("dvh");
  }
  function drawObjPlot() {
    const cv = $("objPlot"), dpr = devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
    cv.width = W * dpr; cv.height = H * dpr; const g = cv.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.fillStyle = "#0b0f14"; g.fillRect(0, 0, W, H);
    const h = ENG.state.history; if (h.length < 2) return;
    const mx = Math.max(...h.slice(1)), mn = Math.min(...h);
    g.strokeStyle = "#8b5cf6"; g.lineWidth = 1.5; g.beginPath();
    h.forEach((v, i) => { const x = 6 + (W - 12) * i / (h.length - 1), y = H - 8 - (H - 20) * (Math.log(v + 1e-6) - Math.log(mn + 1e-6)) / Math.max(1e-6, Math.log(mx + 1e-6) - Math.log(mn + 1e-6)); i ? g.lineTo(x, y) : g.moveTo(x, y); });
    g.stroke(); g.fillStyle = "#8394a7"; g.font = "11px system-ui"; g.fillText(`objective (log) · ${h.length} iterations · ${h[h.length - 1].toFixed(3)}`, 8, 13);
  }

  function rebuild(plan) {
    busy(true, "Preparing beams and dose influence…");
    setTimeout(() => {
      ENG.setup(plan);
      statsCache = null; S.doseVersion++;
      $("cpSlider").max = ENG.state.cps.length - 1;
      isoTable(); objTable(); statsTable(); beamList();
      setCP(Math.min(S.cpIndex, ENG.state.cps.length - 1), false);
      busy(false); req(...ALL);
    }, 30);
  }
  function optimise() {
    play(false);
    const btns = [$("btnOpt"), $("btnOpt2")]; btns.forEach(b => b.disabled = true);
    busy(true, "Optimising fluence (stage 1)…");
    ENG.optimise(200, (i, n, obj) => {
      $("busyText").textContent = `Optimising fluence… iteration ${i}/${n} · objective ${obj.toFixed(3)}`;
      $("optProgress").firstElementChild.style.width = `${100 * i / n}%`;
      if (i % 20 === 0) drawObjPlot();
    }, () => {
      statsCache = null; S.doseVersion++; drawObjPlot(); statsTable(); beamList();
      btns.forEach(b => b.disabled = false); busy(false); setCP(S.cpIndex, false); req(...ALL);
    });
  }
  function finalDose() {
    busy(true, "Final calculation on a 0.5 cm grid…");
    ENG.finalCalc((v, n) => { $("busyText").textContent = `Final calculation on a 0.5 cm grid… ${Math.round(100 * v / n)}%`; },
      () => { statsCache = null; statsTable(); busy(false); req("dvh"); });
  }

  // ------------------------------------------------------------------ screenshot
  function screenshot() {
    flush();
    const ids = ["vRoom", "vBEV", "vDVH", "vAx", "vCor", "vSag"].filter(id => $(id).offsetParent !== null);
    const r0 = $("views").getBoundingClientRect(), dpr = devicePixelRatio || 1;
    const out = document.createElement("canvas"); out.width = r0.width * dpr; out.height = (r0.height + 40) * dpr;
    const g = out.getContext("2d"); g.scale(dpr, dpr); g.fillStyle = "#070a0e"; g.fillRect(0, 0, r0.width, r0.height + 40);
    for (const id of ids) {
      const v = $(id), cv = [...v.querySelectorAll("canvas")].find(c => c.style.display !== "none"), r = cv.getBoundingClientRect();
      g.drawImage(cv, r.left - r0.left, r.top - r0.top, r.width, r.height);
      if (id === "vRoom") { g.fillStyle = "#e8eef5"; g.font = "600 12px system-ui"; g.fillText("Room view", r.left - r0.left + 8, r.top - r0.top + 16);
        g.font = "11px system-ui"; g.textAlign = "right"; $("roomInfo").innerText.split("\n").forEach((t, i) => g.fillText(t, r.right - r0.left - 8, r.top - r0.top + 16 + 14 * i)); g.textAlign = "left"; }
    }
    g.fillStyle = "#9fb3c8"; g.font = "12px system-ui";
    g.fillText("TBI Planning Simulator (educational) · synthetic Rando-like phantom · approximate dose model · not a clinical TPS", 10, r0.height + 25);
    const a = document.createElement("a"); a.download = `TBI_simulator_${Date.now()}.png`; a.href = out.toDataURL("image/png"); a.click();
  }

  // ------------------------------------------------------------------ events
  document.querySelectorAll(".tabs button").forEach(b => b.onclick = () => {
    document.querySelectorAll(".tabs button").forEach(x => x.classList.toggle("on", x === b));
    document.querySelectorAll(".tab").forEach(t => t.classList.toggle("on", t.id === "tab-" + b.dataset.tab));
    if (b.dataset.tab === "obj") drawObjPlot();
  });
  document.querySelectorAll(".vtabs button").forEach(b => b.onclick = () => {
    document.querySelectorAll(".vtabs button").forEach(x => x.classList.toggle("on", x === b));
    S.panel = b.dataset.p; $("cDVH").style.display = S.panel === "dvh" ? "" : "none"; $("cProf").style.display = S.panel === "prof" ? "" : "none"; req("dvh");
  });
  $("btnOpt").onclick = optimise; $("btnOpt2").onclick = optimise; $("btnFinal").onclick = finalDose;
  $("btnPlay").onclick = () => play(!S.playing); $("btnRef").onclick = setReference; $("btnShot").onclick = screenshot;
  $("preset").onchange = e => rebuild(presetPlan(e.target.value));
  $("applyPlan").onclick = () => { const p = ENG.state.plan; p.rx = +$("rx").value; p.fx = +$("fx").value; p.cpStep = +$("cpStep").value; p.smoothing = $("smooth").value; rebuild(p); };
  $("addIso").onclick = () => {
    const I = ENG.state.plan.isos, last = I[I.length - 1];
    I.push({ name: String.fromCharCode(65 + I.length), z: Math.min(PH.LENGTH, last.z + 25), lo: -13.5, hi: 13.5, arcs: 2 }); isoTable(); req("cor", "sag");
  };
  $("smooth").onchange = e => ENG.state.plan.smoothing = e.target.value;
  $("layout").onchange = e => { $("views").className = e.target.value; setTimeout(() => req(...ALL), 50); };
  $("doseMode").onchange = e => { S.doseMode = e.target.value === "iso" ? "iso" : e.target.value; req("ax", "cor", "sag"); };
  $("win").onchange = e => { const [c, w] = e.target.value.split(",").map(Number); S.window = { c, w }; req("ax", "cor", "sag"); };
  const ic = $("isoChecks");
  V2.ISO_LEVELS.forEach(L => {
    const l = document.createElement("label"); l.innerHTML = `<input type="checkbox" checked> <span class="sw" style="background:${L.c}"></span>${L.p}% (${(ENG.state.plan.rx * L.p / 100).toFixed(1)} Gy)`;
    l.querySelector("input").onchange = e => { S.isoLevels[L.p] = e.target.checked; req("ax", "cor", "sag"); }; ic.appendChild(l);
  });
  const sc = $("structChecks");
  PH.STRUCTS.forEach(st => {
    const l = document.createElement("label"); l.innerHTML = `<input type="checkbox" checked> <span class="sw" style="background:${st.color}"></span>${st.id}${st.dvhOnly ? " (DVH)" : ""}`;
    l.querySelector("input").onchange = e => { S.showStruct[st.id] = e.target.checked; req("ax", "cor", "sag", "dvh"); }; sc.appendChild(l);
  });
  const ro = { optTransp: "transparent", optTracks: "showTracks", optBeam: "showBeam", optLasers: "showLasers" };
  for (const id in ro) $(id).onchange = e => { ROOM.opts[ro[id]] = e.target.checked; req("room"); };
  $("optMLC").onchange = e => { S.showMLC = e.target.checked; req("bev"); };
  $("optBeams2d").onchange = e => { S.showBeams = e.target.checked; req("ax"); };
  document.querySelectorAll("[data-cam]").forEach(b => b.onclick = () => { ROOM.resetView(b.dataset.cam); req("room"); });
  $("cpSlider").oninput = e => setCP(+e.target.value, true);
  $("prevCP").onclick = () => setCP(S.cpIndex - 1, true); $("nextCP").onclick = () => setCP(S.cpIndex + 1, true);
  window.addEventListener("keydown", e => {
    if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
    if (e.key === "ArrowRight") setCP(S.cpIndex + 1, true);
    if (e.key === "ArrowLeft") setCP(S.cpIndex - 1, true);
    if (e.key === " ") { play(!S.playing); e.preventDefault(); }
  });
  // slice interaction: wheel = move slice, click = set crosshair
  const bind = (v, key) => {
    v.cv.addEventListener("wheel", e => {
      e.preventDefault(); const d = Math.sign(e.deltaY) * (e.shiftKey ? 2.5 : 0.5);
      if (v.kind === "axial") S.cross.z = Math.max(0.25, Math.min(PH.LENGTH - 0.25, S.cross.z + d));
      else if (v.kind === "coronal") S.cross.y = Math.max(-12, Math.min(12, S.cross.y + d));
      else S.cross.x = Math.max(-17, Math.min(17, S.cross.x + d));
      req("ax", "cor", "sag", ...(S.panel === "prof" ? ["dvh"] : []));
    }, { passive: false });
    v.cv.addEventListener("click", e => {
      const m = v._m; if (!m) return; const r = v.cv.getBoundingClientRect(), u = m.U(e.clientX - r.left), w = m.V(e.clientY - r.top);
      if (v.kind === "axial") { S.cross.x = u; S.cross.y = w; } else if (v.kind === "coronal") { S.cross.x = u; S.cross.z = w; } else { S.cross.y = u; S.cross.z = w; }
      S.cross.z = Math.max(0.25, Math.min(PH.LENGTH - 0.25, S.cross.z));
      req("ax", "cor", "sag", ...(S.panel === "prof" ? ["dvh"] : []));
    });
  };
  bind(views.ax); bind(views.cor); bind(views.sag);
  window.addEventListener("resize", () => req(...ALL));
  ROOM.onChange = () => req("room");

  // ------------------------------------------------------------------ start
  if (!ROOM.init($("cRoom"))) $("roomInfo").innerHTML = "<b>WebGL is not available in this browser</b>";
  rebuild(presetPlan("thesis"));
  window.TBISIM = { S, req, optimise, finalDose, setCP, play, ENG };
})();
