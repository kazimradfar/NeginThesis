// navy_deck.js – Kazim's academic PowerPoint template (measured from "Radfar_Proposal_Defense_Slides_2026-11-08.pptx").
// Wide 16:9 (13.33 × 7.5 in), Times New Roman, navy bars, ❑ / o bullets in navy, light tables, light Thank-You page.
const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

const NAVY = "1F3864", LINE = "8EA9DB", LIGHT = "EEF2F8", ACCENT = "C55A11", GREY = "4A5568", WHITE = "FBFCFE";
const PAGE = "FCFCFA", TEXT = "1E2430", BORDER = "C5CDD8", FOOTTXT = "D6DEEB";
const FONT = "Times New Roman";
const W = 13.333, H = 7.5, HEAD = 0.97, FOOT = 0.44, MX = 0.78, SRC = 0.33;
const BODY_Y = 1.32, TW = W - 2 * MX;                       // text width 11.78 in
const BUL = { 1: "2751", 2: "006F", 3: "2013", "✓": "2713" }; // ❑  o  –  ✓
const NUM = { "1.": "arabicPeriod", "(i)": "romanLcParenBoth", "(a)": "alphaLcParenBoth" };

function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|\[\d{2,3}[A-Z][a-z]?\]|\^\{[^}]+\}|_\{[^}]+\})/g;
  let last = 0, m;
  const push = (t, o = {}) => t && out.push({ text: t, options: { ...base, ...o } });
  while ((m = re.exec(text))) {
    push(text.slice(last, m.index));
    const s = m[0];
    if (s.startsWith("**")) push(s.slice(2, -2), { bold: true });
    else if (s.startsWith("*")) push(s.slice(1, -1), { italic: true });
    else if (s.startsWith("^{")) push(s.slice(2, -1), { superscript: true });
    else if (s.startsWith("_{")) push(s.slice(2, -1), { subscript: true });
    else { const mm = s.match(/\[(\d+)([A-Za-z]+)\]/); push("["); push(mm[1], { superscript: true }); push(mm[2] + "]"); }
    last = m.index + s.length;
  }
  push(text.slice(last));
  return out.length ? out : [{ text: "", options: base }];
}

// items: "text" (level 1) | [2, "text"] | [3, "text"] | ["✓", "text"] | ["1.", "numbered"] | ["(i)", "roman"]
//        | ["h", "Sub-heading"] (navy bold line, no bullet)
function bulletRuns(items, size = 15, opts = {}) {
  const out = [];
  let numCount = {};
  items.forEach((it, i) => {
    const [lvl, txt] = Array.isArray(it) ? it : [1, it];
    let rs;
    if (lvl === "h") {
      rs = runs(txt, { fontSize: size + 1, bold: true, color: NAVY });
      Object.assign(rs[0].options, { bullet: false, paraSpaceBefore: i ? 6 : 0, paraSpaceAfter: 4 });
      numCount = {};
    } else {
      const num = NUM[lvl];
      const depth = num || lvl === "✓" ? 1 : lvl;
      rs = runs(txt, { fontSize: size - (depth > 1 ? 1 : 0) - (depth > 2 ? 1 : 0), color: TEXT });
      if (opts.boldTop) rs.forEach(r => { if (depth === 1 && r.options.bold === undefined) r.options.bold = true; });
      let bullet;
      if (num) { numCount[lvl] = (numCount[lvl] || 0) + 1; bullet = { type: "number", style: num, startAt: numCount[lvl] }; }
      else { numCount = {}; bullet = { code: BUL[lvl] || BUL[depth] }; }
      Object.assign(rs[0].options, { bullet, indentLevel: depth - 1,
        paraSpaceAfter: depth === 1 ? (opts.space ?? 13) : 10 });
    }
    rs[rs.length - 1].options.breakLine = i < items.length - 1;
    out.push(...rs);
  });
  return out;
}

function bodyH(sp) { return H - FOOT - BODY_Y - 0.12 - (sp.source ? SRC : 0); }
function newSlide(pres) { return pres._section ? pres.addSlide({ sectionTitle: pres._section }) : pres.addSlide(); }
const box = (o) => ({ margin: 0, isTextBox: true, fontFace: FONT, ...o });

function bars(pres, s) {
  s.background = { color: PAGE };
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: W, h: HEAD, fill: { color: NAVY }, line: { color: NAVY } });
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: HEAD, w: W, h: 0.04, fill: { color: LINE }, line: { color: LINE } });
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: H - FOOT, w: W, h: FOOT, fill: { color: NAVY }, line: { color: NAVY } });
}

function frame(pres, s, sp, n) {
  bars(pres, s);
  if (sp.title) s.addText(runs(sp.title, { fontSize: 25, bold: true, color: WHITE, fontFace: FONT }),
    box({ x: MX, y: 0, w: TW, h: HEAD, valign: "middle", fit: "shrink" }));
  s.addText(String(n), box({ x: W - MX - 1.43, y: H - FOOT, w: 1.43, h: FOOT, fontSize: 12, color: WHITE,
    align: "right", valign: "middle" }));
  if (pres._footerText) s.addText(pres._footerText, box({ x: MX, y: H - FOOT, w: 9.07, h: FOOT, fontSize: 12,
    color: FOOTTXT, valign: "middle" }));
  if (sp.source) s.addText(runs(sp.source, { fontSize: 12, italic: true, color: GREY, fontFace: FONT }),
    box({ x: MX, y: H - FOOT - SRC, w: TW, h: 0.26, valign: "middle", fit: "shrink" }));
  if (sp.notes) s.addNotes(sp.notes);
}

function figure(pres, s, f, x, y, w, h) {
  if (f.path && fs.existsSync(f.path)) {
    const capH = f.caption ? 0.34 : 0;
    const img = { path: f.path, x, y, w, h: h - capH };
    if (f.size) {
      const r = Math.min(w / f.size[0], (h - capH) / f.size[1]);
      img.w = f.size[0] * r; img.h = f.size[1] * r;
      img.x = x + (w - img.w) / 2; img.y = y + (h - capH - img.h) / 2;
    }
    s.addImage(img);
    if (f.caption) s.addText(runs(f.caption, { fontSize: 12, italic: true, color: GREY, fontFace: FONT }),
      box({ x, y: img.y + img.h + 0.04, w, h: 0.3, align: "center", fit: "shrink" }));
  } else {
    s.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: LIGHT }, line: { color: "B4C6E7", dashType: "dash" } });
    s.addText(runs(`📌 ${f.label || "Figure"}${f.caption ? ": " + f.caption : ""}`, { fontSize: 15, color: NAVY, fontFace: FONT }),
      box({ x, y, w, h, align: "center", valign: "middle", margin: 6 }));
  }
}

function callout(pres, s, text, x, y, w, h) {
  s.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: LIGHT }, line: { color: NAVY, width: 1 } });
  s.addText(runs(text, { fontSize: 15, color: TEXT, fontFace: FONT }),
    box({ x: x + 0.23, y, w: w - 0.46, h, valign: "middle", fit: "shrink" }));
}

// navy bold column heading with a thin light-blue rule under it (as on the gap / twocol slides)
function colHead(pres, s, text, x, y, w) {
  s.addText(runs(text, { fontSize: 17, bold: true, color: NAVY, fontFace: FONT }), box({ x, y, w, h: 0.35, valign: "middle", fit: "shrink" }));
  s.addShape(pres.shapes.LINE, { x, y: y + 0.36, w, h: 0, line: { color: LINE, width: 1 } });
  return y + 0.48;
}

function table(pres, s, t, x, y, w) {
  const size = t.size || 13;
  const head = t.head.map(c => ({ text: runs(c, { bold: true, color: WHITE, fontSize: size, fontFace: FONT }),
    options: { fill: { color: NAVY } } }));
  const rows = t.rows.map((r, i) => r.map((c, j) => ({ text: runs(String(c), { fontSize: size, color: TEXT, fontFace: FONT,
    bold: j === 0 && t.boldFirst ? true : undefined }), options: { fill: { color: i % 2 ? LIGHT : PAGE } } })));
  const colW = t.colW ? t.colW.map(c => c * w / t.colW.reduce((a, b) => a + b, 0)) : undefined;
  s.addTable([head, ...rows], { x, y, w, colW, valign: "top", border: { type: "solid", pt: 0.75, color: BORDER },
    margin: [0.06, 0.11, 0.06, 0.11], autoPage: false });
}

// one column of content: {h, items, table, callout} – used by twocol
function column(pres, s, col, x, y, w, bottom, size) {
  if (col.h) y = colHead(pres, s, col.h, x, y, w);
  const ch = col.callout ? 0.7 : 0;
  if (col.items) {
    const th = col.table ? Math.min(bottom - y, (col.itemsH || 0.42 * col.items.length + 0.1)) : bottom - y - (ch ? ch + 0.12 : 0);
    s.addText(bulletRuns(col.items, size), box({ x, y, w, h: th, valign: "top", fit: "shrink" }));
    y += col.table ? th + 0.1 : 0;
  }
  if (col.table) table(pres, s, { size: size - 1, ...col.table }, x, y, w);
  if (col.callout) callout(pres, s, col.callout, x, bottom - ch, w, ch);
}

const SLIDES = {
  cover(pres, sp) {
    const s = newSlide(pres);
    s.background = { color: PAGE };
    s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: W, h: 1.04, fill: { color: NAVY }, line: { color: NAVY } });
    s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 1.04, w: W, h: 0.04, fill: { color: LINE }, line: { color: LINE } });
    s.addShape(pres.shapes.RECTANGLE, { x: 0, y: H - FOOT, w: W, h: FOOT, fill: { color: NAVY }, line: { color: NAVY } });
    s.addText(sp.institution || "", box({ x: MX, y: 0.2, w: TW, h: 0.42, fontSize: 18, bold: true, color: WHITE, align: "center", valign: "middle" }));
    if (sp.department) s.addText(sp.department, box({ x: MX, y: 0.6, w: TW, h: 0.3, fontSize: 13, color: FOOTTXT, align: "center", valign: "middle" }));
    if (sp.kind) s.addText(sp.kind, box({ x: MX, y: 2.32, w: TW, h: 0.4, fontSize: 14, italic: true, color: GREY, align: "center", valign: "middle" }));
    s.addText(runs(sp.title, { fontSize: 20, bold: true, color: NAVY, fontFace: FONT }),
      box({ x: 1.67, y: 2.85, w: W - 3.34, h: 1.75, align: "center", valign: "middle", fit: "shrink" }));
    s.addShape(pres.shapes.LINE, { x: W / 2 - 1.46, y: 4.79, w: 2.92, h: 0, line: { color: LINE, width: 1 } });
    const ppl = sp.people || [];
    const cw = Math.min(4.6, (W - 2 * MX) / Math.max(ppl.length, 1)), x0 = (W - cw * ppl.length) / 2;
    ppl.forEach((p, i) => {
      s.addText(p.role, box({ x: x0 + i * cw, y: 5.08, w: cw, h: 0.28, fontSize: 12, color: GREY, align: "center", valign: "middle" }));
      s.addText(p.name, box({ x: x0 + i * cw, y: 5.36, w: cw, h: 0.32, fontSize: 14, bold: true, color: TEXT, align: "center", valign: "middle", fit: "shrink" }));
    });
    (sp.lines || []).forEach((l, i) => s.addText(runs(l, { fontSize: 13, italic: true, color: GREY, fontFace: FONT }),
      box({ x: MX, y: 5.95 + i * 0.32, w: TW, h: 0.3, align: "center" })));
    s.addText(sp.date || "", box({ x: MX, y: H - FOOT, w: TW, h: FOOT, fontSize: 12, color: FOOTTXT, align: "center", valign: "middle" }));
    if (sp.notes) s.addNotes(sp.notes);
  },
  outline(pres, sp, n) {                                // items default to the sections that follow this slide
    const s = newSlide(pres);
    frame(pres, s, { ...sp, title: sp.title || "Outline" }, n);
    const items = sp.items || pres._sectionsAfter(n);
    s.addText(bulletRuns(items, sp.size || 17, { space: 20 }),
      box({ x: MX, y: BODY_Y + 0.07, w: TW, h: bodyH(sp) - 0.1, valign: "top", fit: "shrink" }));
  },
  section(pres, sp) {                                   // optional navy divider slide
    const s = newSlide(pres);
    s.background = { color: NAVY };
    s.addText(runs(sp.title, { fontSize: 34, bold: true, color: WHITE, fontFace: FONT }),
      box({ x: MX, y: 2.6, w: TW, h: 1.1, align: "center", valign: "middle" }));
    if (sp.subtitle) s.addText(runs(sp.subtitle, { fontSize: 19, italic: true, color: FOOTTXT, fontFace: FONT }),
      box({ x: MX, y: 3.75, w: TW, h: 0.6, align: "center" }));
    if (sp.notes) s.addNotes(sp.notes);
  },
  bullets(pres, sp, n) {                                // optional figure (right), callout (bottom)
    const s = newSlide(pres);
    frame(pres, s, sp, n);
    const fig = sp.figure, bh = bodyH(sp), ch = sp.callout ? (sp.calloutH || 0.6) : 0;
    const tw = fig ? TW - (fig.width || 5.2) - 0.35 : TW;
    s.addText(bulletRuns(sp.items, sp.size || 15), box({ x: MX, y: BODY_Y, w: tw, h: bh - (ch ? ch + 0.15 : 0), valign: "top", fit: "shrink" }));
    if (fig) { const fx = MX + tw + 0.35; figure(pres, s, fig, fx, BODY_Y, W - MX - fx, bh - (ch ? ch + 0.15 : 0)); }
    if (sp.callout) callout(pres, s, sp.callout, MX, sp.calloutY || BODY_Y + bh - ch, TW, ch);
  },
  table(pres, sp, n) {                                  // optional lead line above, items + callout + note below
    const s = newSlide(pres);
    frame(pres, s, sp, n);
    let y = BODY_Y - 0.07;
    if (sp.lead) {
      s.addText(bulletRuns([sp.lead], 15), box({ x: MX, y: y + 0.07, w: TW, h: 0.4, valign: "top", fit: "shrink" }));
      y += 0.53;
    }
    table(pres, s, sp, MX, y, TW);
    if (sp.items) s.addText(bulletRuns(sp.items, 15), box({ x: MX, y: sp.itemsY || y + 0.42 * (sp.rows.length + 1) + 0.25,
      w: TW, h: 1.2, valign: "top", fit: "shrink" }));
    if (sp.callout) callout(pres, s, sp.callout, MX, sp.calloutY || BODY_Y + bodyH(sp) - 0.6, TW, 0.6);
    if (sp.note) s.addText(runs(sp.note, { fontSize: 13, italic: true, color: GREY, fontFace: FONT }),
      box({ x: MX, y: BODY_Y + bodyH(sp) - 0.36, w: TW, h: 0.36, fit: "shrink" }));
  },
  twocol(pres, sp, n) {                                 // left/right: {h, items, table, callout}; optional full-width callout
    const s = newSlide(pres);
    frame(pres, s, sp, n);
    const gap = 0.34, cw = (TW - gap) / 2, ch = sp.callout ? 0.7 : 0;
    const bottom = BODY_Y + bodyH(sp) - (ch ? ch + 0.15 : 0);
    [sp.left, sp.right].forEach((col, i) => column(pres, s, col, MX + i * (cw + gap), BODY_Y - 0.02, cw, bottom, sp.size || 14));
    if (sp.callout) callout(pres, s, sp.callout, MX, sp.calloutY || bottom + 0.15, TW, ch);
  },
  flow(pres, sp, n) {                                   // boxes with arrows; steps: [{h, t, color?, fill?}]
    const s = newSlide(pres);
    frame(pres, s, sp, n);
    const k = sp.steps.length, gap = 0.36, top = BODY_Y + 0.05;
    const bw = (TW - gap * (k - 1)) / k, bh = sp.boxH || 3.0;
    sp.steps.forEach((st, i) => {
      const x = MX + i * (bw + gap), c = st.color || NAVY;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: top, w: bw, h: bh, rectRadius: 0.08,
        fill: { color: st.fill ? c : WHITE }, line: { color: c, width: 1.5 } });
      s.addText(runs(st.h, { fontSize: 14, bold: true, color: st.fill ? WHITE : c, fontFace: FONT }),
        box({ x: x + 0.08, y: top + 0.08, w: bw - 0.16, h: 0.6, align: "center", valign: "middle", fit: "shrink" }));
      s.addText(runs(st.t, { fontSize: 12.5, color: st.fill ? WHITE : TEXT, fontFace: FONT }),
        box({ x: x + 0.12, y: top + 0.75, w: bw - 0.24, h: bh - 0.85, valign: "top", fit: "shrink" }));
      if (i < k - 1) s.addShape(pres.shapes.RIGHT_ARROW, { x: x + bw + 0.05, y: top + bh / 2 - 0.13, w: gap - 0.1, h: 0.26,
        fill: { color: GREY }, line: { color: GREY } });
    });
    if (sp.items) s.addText(bulletRuns(sp.items, 15), box({ x: MX, y: top + bh + 0.25, w: TW,
      h: BODY_Y + bodyH(sp) - (top + bh + 0.25), valign: "top", fit: "shrink" }));
  },
  images(pres, sp, n) {                                 // 1–3 figures side by side, optional items below
    const s = newSlide(pres);
    frame(pres, s, sp, n);
    const k = sp.figures.length, gap = 0.3, bh = bodyH(sp);
    const fw = (TW - gap * (k - 1)) / k, itemsH = sp.items ? 0.42 * sp.items.length + 0.1 : 0;
    const ar = Math.max(...sp.figures.map(f => f.size ? f.size[1] / f.size[0] : 0.6));
    const fh = Math.min(bh - itemsH - 0.1, fw * ar + 0.34);
    const top = BODY_Y + Math.max(0, (bh - fh - itemsH) / 2);
    sp.figures.forEach((f, i) => figure(pres, s, f, MX + i * (fw + gap), top, fw, fh));
    if (sp.items) s.addText(bulletRuns(sp.items, 15), box({ x: MX, y: top + fh + 0.12, w: TW, h: itemsH, valign: "top", fit: "shrink" }));
  },
  gantt(pres, sp, n) {                                  // rows: [{t, a, b}] months a–b (1-based)
    const s = newSlide(pres);
    frame(pres, s, sp, n);
    const months = sp.months || 24, cols = sp.cols || ["Months 1–6", "7–12", "13–18", "19–24"];
    const lw = sp.labelW || 5.0, bx = MX + lw + 0.15, bw = W - MX - bx;
    const rowH = Math.min(0.37, (bodyH(sp) - 0.45) / sp.rows.length), hy = BODY_Y - 0.07;
    s.addShape(pres.shapes.RECTANGLE, { x: MX, y: hy, w: TW, h: 0.34, fill: { color: NAVY }, line: { color: NAVY } });
    s.addText(sp.labelHead || "Activity (months)", box({ x: MX + 0.1, y: hy, w: lw, h: 0.34, fontSize: 12.5, bold: true, color: WHITE, valign: "middle" }));
    cols.forEach((c, i) => s.addText(c, box({ x: bx + i * bw / cols.length, y: hy, w: bw / cols.length, h: 0.34,
      fontSize: 12.5, bold: true, color: WHITE, valign: "middle" })));
    sp.rows.forEach((r, i) => {
      const y = hy + 0.44 + i * rowH;
      s.addText(runs(r.t, { fontSize: 12.5, color: TEXT, fontFace: FONT }), box({ x: MX + 0.1, y, w: lw, h: rowH, valign: "middle", fit: "shrink" }));
      s.addShape(pres.shapes.RECTANGLE, { x: bx, y: y + rowH * 0.2, w: bw, h: rowH * 0.6, fill: { color: LIGHT }, line: { color: LIGHT } });
      s.addShape(pres.shapes.RECTANGLE, { x: bx + bw * (r.a - 1) / months, y: y + rowH * 0.2, w: bw * (r.b - r.a + 1) / months,
        h: rowH * 0.6, fill: { color: r.color || NAVY }, line: { color: r.color || NAVY } });
    });
  },
  references(pres, sp, n) {                             // two columns, numbered continuously
    const s = newSlide(pres);
    frame(pres, s, { ...sp, title: sp.title || "Key references" }, n);
    const gap = 0.34, cw = (TW - gap) / 2, bh = bodyH(sp);
    [sp.left || [], sp.right || []].forEach((list, i) => {
      const off = i ? (sp.left || []).length : 0, rs = [];
      list.forEach((r, j) => {
        const rr = runs(`${off + j + 1}. ${r}`, { fontSize: sp.size || 12.5, color: TEXT, fontFace: FONT });
        rr[0].options.paraSpaceAfter = 7;
        rr[rr.length - 1].options.breakLine = j < list.length - 1 || (!i && !!sp.note);
        rs.push(...rr);
      });
      if (!i && sp.note) rs.push(...runs(sp.note, { fontSize: 12, italic: true, color: GREY, fontFace: FONT }));
      s.addText(rs, box({ x: MX + i * (cw + gap), y: BODY_Y - 0.05, w: cw, h: bh, valign: "top", fit: "shrink" }));
    });
  },
  thanks(pres, sp, n) {                                 // light page with the bars, as in the defence deck
    const s = newSlide(pres);
    frame(pres, s, { notes: sp.notes }, n);
    s.addText("Thank You", box({ x: MX, y: 3.15, w: TW, h: 1.05, fontSize: 55, bold: true, color: NAVY, align: "center", valign: "middle" }));
    s.addShape(pres.shapes.LINE, { x: W / 2 - 1.8, y: 4.32, w: 3.6, h: 0, line: { color: LINE, width: 1.5 } });
    s.addText(runs(sp.subtitle || "Questions and comments are welcome", { fontSize: 19, italic: true, color: GREY, fontFace: FONT }),
      box({ x: MX, y: 4.5, w: TW, h: 0.45, align: "center", valign: "middle" }));
    (sp.lines || []).forEach((l, i) => s.addText(runs(l, { fontSize: 14, color: GREY, fontFace: FONT }),
      box({ x: MX, y: 5.15 + i * 0.32, w: TW, h: 0.3, align: "center" })));
  },
};

async function build(spec, outFile) {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE";                          // 13.33 × 7.5 in
  pres.author = spec.author || "";
  pres.title = spec.title || "";
  pres.theme = { headFontFace: FONT, bodyFontFace: FONT };
  pres._footerText = spec.footer || "";
  const slides = [...spec.slides];
  if (!slides.some(s => s.type === "thanks")) slides.push({ type: "thanks", lines: spec.thanks || [] });
  // sections: a slide without `section` stays in the previous one; the first defaults to "Title"
  const useSections = slides.some(s => s.section);
  let cur = null;
  slides.forEach(sp => { sp._section = useSections ? (sp.section || cur || "Title") : null; cur = sp._section; });
  const skip = new Set(spec.outlineSkip || ["Title", "Closing"]);
  pres._sectionsAfter = n => [...new Set(slides.slice(n).map(s => s._section))].filter(x => x && !skip.has(x));
  cur = null;
  slides.forEach((sp, i) => {
    const fn = SLIDES[sp.type];
    if (!fn) throw new Error("unknown slide type " + sp.type);
    if (sp._section && sp._section !== cur) { pres.addSection({ title: sp._section }); cur = sp._section; }
    pres._section = sp._section;
    fn(pres, sp, i + 1);
  });
  await pres.writeFile({ fileName: outFile });
  await fixParagraphs(outFile);
  return outFile;
}

// pptxgenjs writes an <a:pPr> before every run of a multi-run paragraph (later ones say "no bullet"), which removes
// the bullet of any bullet with bold/superscript words: keep only the first <a:pPr>. Also colour every bullet navy.
async function fixParagraphs(file) {
  let JSZip;
  try { JSZip = require("jszip"); } catch (e) { JSZip = require(require.resolve("jszip", { paths: [path.dirname(require.resolve("pptxgenjs"))] })); }
  const zip = await JSZip.loadAsync(fs.readFileSync(file));
  for (const name of Object.keys(zip.files).filter(n => /^ppt\/slides\/slide\d+\.xml$/.test(n))) {
    const xml = await zip.file(name).async("string");
    const fixed = xml.replace(/<a:p>([\s\S]*?)<\/a:p>/g, (whole, inner) => {
      let seen = false;
      let body = inner.replace(/<a:pPr\b[^>]*\/>|<a:pPr\b[^>]*>[\s\S]*?<\/a:pPr>/g, m => {
        if (!seen && inner.indexOf(m) === inner.search(/\S/)) { seen = true; return m; }
        return "";
      });
      body = body.replace(/(<a:pPr\b[^>]*>)([\s\S]*?)(<\/a:pPr>)/, (m, a, b, c) =>
        /<a:bu(Char|AutoNum)/.test(b) && !/<a:buClr>/.test(b)
          ? a + b.replace(/(<a:bu(Sz|Font|Char|AutoNum))/, '<a:buClr><a:srgbClr val="' + NAVY + '"/></a:buClr>$1') + c : m);
      return "<a:p>" + body + "</a:p>";
    });
    zip.file(name, fixed);
  }
  fs.writeFileSync(file, await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
}

module.exports = { build, runs };
