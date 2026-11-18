// Uzilmas — umumiy yordamçilar
const API = location.origin.startsWith("http") ? "" : "http://127.0.0.1:8000";
// ---------- Til: özbekça (yangi alifbo) / ruscha ----------
const LANG = (() => {
  let l = null;
  try { l = new URLSearchParams(location.search).get("lang") || localStorage.getItem("uzilmas_lang"); } catch (e) {}
  if (!l) {
    const tg = window.Telegram && Telegram.WebApp && Telegram.WebApp.initDataUnsafe && Telegram.WebApp.initDataUnsafe.user;
    if (tg && /^ru/.test(tg.language_code || "")) l = "ru";
  }
  return l === "ru" ? "ru" : "uz";
})();
document.documentElement.lang = LANG;
const RU = (typeof RU_DICT !== "undefined") ? RU_DICT : {};   // i18n-ru.js (common.js dan oldin yuklanadi)
const I18N_MISSING = new Set();
function t(uz, ...args) {
  let s = uz;
  if (LANG === "ru") {
    if (uz in RU) s = RU[uz]; else if (!I18N_MISSING.has(uz)) { I18N_MISSING.add(uz); console.warn("i18n missing:", uz); }
  }
  args.forEach((a, i) => { s = s.split("{" + i + "}").join(a); });
  return s;
}
function i18n(root = document) {
  root.querySelectorAll("[data-t]").forEach(el => { el.innerHTML = t(el.innerHTML.trim().replace(/\s+/g, " ")); });
  root.querySelectorAll("[data-tp]").forEach(el => { el.placeholder = t(el.placeholder); });
  root.querySelectorAll("[data-tt]").forEach(el => { el.title = t(el.title); });
  if (document.title) document.title = t(document.title);
}
function setLang(l) { try { localStorage.setItem("uzilmas_lang", l); } catch (e) {} location.reload(); }
function langSwitch() {
  return `<div class="langsw">${["uz", "ru"].map(l => `<button class="${l === LANG ? "on" : ""}" onclick="setLang('${l}')">${l === "uz" ? "Özb" : "Рус"}</button>`).join("")}</div>`;
}

const ZONE = {
  red: { uz: t("Qizil"), cls: "z-red", long: t("Qizil — darhol") },
  yellow: { uz: t("Sariq"), cls: "z-yellow", long: t("Sariq — kuzatuv") },
  green: { uz: t("Yaşil"), cls: "z-green", long: t("Yaşil — reja böyiça") },
};

// Logotip: uzilmas zanjir halqasi
const LOGO = `<img class="mark" src="/static/logo-mark.png" alt="Uzilmas" style="border-radius:8px">`;

const ICONS = {
  camera: '<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3z"/><circle cx="12" cy="13" r="3"/>',
  mic: '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><path d="M12 19v3"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
  bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
  home: '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 22V12h6v10"/>',
  user: '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  grid: '<rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/>',
  steth: '<path d="M4.8 2.3A.3.3 0 1 0 5 2H4a2 2 0 0 0-2 2v5a6 6 0 0 0 12 0V4a2 2 0 0 0-2-2h-1a.2.2 0 1 0 .3.3"/><path d="M8 15v1a6 6 0 0 0 12 0v-4"/><circle cx="20" cy="10" r="2"/>',
  activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10"/><path d="m9 12 2 2 4-4"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  checkc: '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  phone: '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8.1 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.9.6 2.8.7a2 2 0 0 1 1.7 2z"/>',
  wifi: '<path d="M5 13a10 10 0 0 1 14 0"/><path d="M8.5 16.5a5 5 0 0 1 7 0"/><path d="M2 8.8a15 15 0 0 1 20 0"/><path d="M12 20h.01"/>',
  wifioff: '<path d="m2 2 20 20"/><path d="M8.5 16.5a5 5 0 0 1 7 0"/><path d="M5 12.9a10 10 0 0 1 5.2-2.7"/><path d="M19 12.9a10 10 0 0 0-2-1.6"/><path d="M2 8.8a15 15 0 0 1 4.2-2.6"/><path d="M10.7 5c4-.4 8.1.9 11.3 3.8"/><path d="M12 20h.01"/>',
  alert: '<path d="m21.7 18-8-14a2 2 0 0 0-3.5 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  arrow: '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
  back: '<path d="m15 18-6-6 6-6"/>',
  up: '<path d="M12 19V5"/><path d="m5 12 7-7 7 7"/>',
  trend: '<path d="M22 7 13.5 15.5 8.5 10.5 2 17"/><path d="M16 7h6v6"/>',
  hospital: '<path d="M12 6v4"/><path d="M14 8h-4"/><path d="M14 14h-4"/><path d="M14 18h-4"/><path d="M18 12h2a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2h2"/><path d="M18 22V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v18"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  send: '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
  spark: '<path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/>',
  pin: '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
  drop: '<path d="M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.5s-3.5-4-4-6.5c-.5 2.5-2 4.9-4 6.5C6 11.1 5 13 5 15a7 7 0 0 0 7 7z"/>',
  file: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.8 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
  help: '<circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
  heart: '<path d="M19 14c1.5-1.5 3-3.2 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.8 0-3 .5-4.5 2-1.5-1.5-2.7-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4 3 5.5l7 7Z"/>',
};
function ic(name, size) {
  const s = size ? ` style="width:${size}px;height:${size}px"` : "";
  return `<svg class="i" viewBox="0 0 24 24"${s} aria-hidden="true">${ICONS[name] || ""}</svg>`;
}

// ---------- Kiriş: har bir xodimning öz logini, har bir rol — öz bölimi ----------
ICONS.desk = '<path d="M3 21h18"/><path d="M5 21V8h14v13"/><path d="M9 21v-5h6v5"/><path d="M9 3h6v5H9z"/>';
ICONS.logout = '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>';
ICONS.chat = '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>';
ICONS.crown = '<path d="m2 4 3 12h14l3-12-6 7-4-7-4 7-6-7z"/><path d="M5 20h14"/>';
let USER = null;
try { USER = JSON.parse(localStorage.getItem("uzilmas_user") || "null"); } catch (e) {}
function token() { try { return localStorage.getItem("uzilmas_token") || ""; } catch (e) { return ""; } }
const ROLE_PAGES = {
  qabul: ["/reception"], hamshira: ["/nurse"], shifokor: ["/dashboard", "/doctor"],
  bosh: ["/dashboard", "/reception", "/nurse", "/doctor"], bemor: ["/patient"],
};
// Sahifa faqat ruxsat etilgan rollarga oçiladi; boşqa rol öz sahifasiga, kirmagan — /login ga
function guardPage(roles) {
  if (!USER || !token()) { location.replace("/login?next=" + encodeURIComponent(location.pathname + location.search)); throw new Error("login"); }
  if (roles && !roles.includes(USER.role)) { location.replace(USER.home || "/"); throw new Error("role"); }
  return USER;
}
async function logout() {
  try { await api("/api/logout", { method: "POST" }); } catch (e) {}
  try { localStorage.removeItem("uzilmas_token"); localStorage.removeItem("uzilmas_user"); } catch (e) {}
  location.href = "/login";
}

// Yagona yuqori panel (barça sahifalarda bir xil)
const PAGES = [
  ["/reception", "desk", t("Qabulxona")],
  ["/dashboard", "grid", t("Mutaxassis paneli")],
  ["/nurse", "user", t("Hamşira")],
  ["/doctor", "steth", t("Oilaviy şifokor")],
  ["/patient", "heart", t("Bemor kabineti")],
];
function topbar(active, right = "") {
  const el = document.getElementById("topbar"); if (!el) return;
  el.className = "topbar";
  const allowed = USER ? (ROLE_PAGES[USER.role] || []) : [];
  const pages = PAGES.filter(([h]) => allowed.includes(h));
  const userChip = USER ? `<div class="userchip" title="${esc(USER.username)}">${ic(USER.role === "bemor" ? "heart" : "user", 15)}
      <div><b>${esc(USER.full_name)}</b><small>${esc(LANG === "ru" ? USER.role_ru : USER.role_uz)}</small></div>
      <button onclick="logout()" title="${t("Çiqiş")}">${ic("logout", 15)}</button></div>`
    : `<a class="btn btn-primary btn-sm" href="/login">${t("Kiriş")}</a>`;
  el.innerHTML = `<div class="in">
    <a class="brand" href="${USER ? USER.home : "/"}">${LOGO}<div>Uzilmas<small>${t("Bemor zanjiri uzilmaydi")}</small></div></a>
    <nav class="nav">${pages.length > 1 ? pages.map(([h, i, title]) => `<a href="${h}" class="${h === active ? "on" : ""}">${ic(i)}<span>${title}</span></a>`).join("") : ""}</nav>
    <div class="right">${right}${langSwitch()}${userChip}</div></div>`;
}

async function api(path, opts = {}) {
  const headers = opts.body && !(opts.body instanceof FormData) ? { "Content-Type": "application/json" } : {};
  if (token()) headers.Authorization = "Bearer " + token();
  const r = await fetch(API + path + (path.includes("?") ? "&" : "?") + "lang=" + LANG, { ...opts, headers });
  if (r.status === 401 && !path.startsWith("/api/login")) {
    try { localStorage.removeItem("uzilmas_token"); localStorage.removeItem("uzilmas_user"); } catch (e) {}
    location.replace("/login?next=" + encodeURIComponent(location.pathname + location.search));
    throw new Error("login");
  }
  if (!r.ok) {
    let msg = r.status + "";
    try { msg = (await r.json()).detail || msg; } catch (e) {}
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return r.json();
}

function zonePill(z) {
  const Z = ZONE[z];
  return `<span class="pill ${Z.cls}"><span class="dot ${z}"></span>${Z.uz}</span>`;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function toast(msg, ms = 2600) {
  let t = document.querySelector(".toast");
  if (!t) { t = document.createElement("div"); t.className = "toast"; document.body.appendChild(t); }
  t.textContent = msg; t.classList.add("show");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("show"), ms);
}

function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    [0, 0.22].forEach((d) => {
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.frequency.value = 880; o.connect(g); g.connect(ctx.destination);
      g.gain.setValueAtTime(0.18, ctx.currentTime + d);
      g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + d + 0.18);
      o.start(ctx.currentTime + d); o.stop(ctx.currentTime + d + 0.2);
    });
  } catch (e) {}
}

const FIELD_LABELS = {
  sbp: t("Bosim (yuqori)"), dbp: t("Bosim (pastki)"), hb_g_l: t("Gemoglobin, g/l"),
  protein_g_l: t("Siydikda oqsil, g/l"), glucose_fasting: t("Glyukoza, mmol/l"), ga_weeks: t("Muddat, hafta"),
};
const SIGNS = {
  severe_headache: t("Kuçli boş oğriği"), blurred_vision: t("Köriş xiralaşgan"),
  vaginal_bleeding: t("Qon ketiş"), convulsions: t("Tutqanoq"), reduced_fetal_movement: t("Homila harakati kam"),
  severe_abdominal_pain: t("Qorinda kuçli oğriq"), high_fever: t("Yuqori isitma"),
};

function fmtTime(s) { return s ? s.replace("T", " ").slice(0, 16) : "—"; }

// ---------- Jonli zanjir ----------
const CHAIN_ICON = { ok: "check", wait: "clock", broken: "alert", next: "more", skip: "minus" };
ICONS.more = '<circle cx="12" cy="12" r="1.5"/>';
ICONS.minus = '<path d="M5 12h14"/>';
function fmtLeft(due) {
  const ms = new Date(due.replace(" ", "T")) - new Date();
  if (ms <= 0) return "";
  const s = Math.floor(ms / 1000), h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), sec = s % 60;
  return `${h ? h + ":" : ""}${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}
function chainLeft(due) {   // matn har soniyada tick() orqali yangilanadi — sahifa qayta çizilmaydi
  return due ? `<span class="cd" data-due="${esc(due)}"></span>` : "";
}
// Faqat soatlarni yangilaydi (DOM qayta yaratilmaydi -> miltillaş yöq)
function tickCountdowns() {
  document.querySelectorAll(".cd[data-due]").forEach(el => {
    const v = fmtLeft(el.dataset.due);
    const txt = v ? ` · ${t("qoldi")} ${v}` : "";
    if (el.textContent !== txt) el.textContent = txt;
  });
}
setInterval(tickCountdowns, 1000);
// HTML faqat özgarganda yoziladi — animatsiyalar qayta boşlanmaydi
function setHTML(el, html) {
  if (typeof el === "string") el = document.getElementById(el);
  if (!el || el._html === html) return false;
  el.innerHTML = html; el._html = html; tickCountdowns();
  return true;
}
function chainPill(st, at) {
  if (st === "broken") return `<span class="pill z-red">${ic("alert", 14)}${t("Uzildi")}${at ? " · " + esc(at) : ""}</span>`;
  if (st === "wait") return `<span class="pill z-yellow">${ic("clock", 14)}${t("Javob kutilmoqda")}</span>`;
  return `<span class="pill" style="background:var(--blue-50);color:var(--blue-700);border-color:var(--blue-100)">${ic("link", 14)}${t("Uzluksiz")}</span>`;
}
function chainHTML(ch, mode = "v") {
  const L = ch.links;
  return `<div class="chain-${mode}">${L.map((l, i) => {
    const nxt = L[i + 1] ? "to-" + L[i + 1].status : "";
    return `<div class="cl s-${l.status} ${nxt}"><div class="cnode s-${l.status}">${ic(CHAIN_ICON[l.status])}</div>
      <div><div class="cl-title">${esc(l.title)}${l.status === "broken" ? `<span class="cl-flag">${t("UZILDI")}</span>` : ""}</div>
      <div class="cl-who">${esc(l.who)}</div>
      <div class="cl-note">${esc(l.note)}${l.status === "wait" ? chainLeft(l.due_at) : ""}</div></div></div>`;
  }).join("")}</div>`;
}
function chainBanner(ch) {
  if (ch.status === "broken") return `<div class="chain-banner">${ic("alert", 16)}<span><b>${t("Harakat kerak:")}</b> ${esc(ch.reason)}</span></div>`;
  if (ch.status === "wait") return `<div class="chain-banner wait">${ic("clock", 16)}<span>${esc(ch.break_at)}: ${esc(ch.reason)}</span></div>`;
  return `<div class="chain-banner ok">${ic("link", 16)}<span>${t("Barça böğinlar işlayapti — bemor nazoratda.")}</span></div>`;
}

// ---------- Yöriqnoma: har bir sahifa nima qilişini 3 qadamda tuşuntiradi ----------
function guide(key, title, sub, steps, force) {
  try { if (!force && localStorage.getItem("uzilmas_guide_" + key)) return; } catch (e) {}
  const bg = document.createElement("div"); bg.className = "guide-bg";
  bg.innerHTML = `<div class="guide"><h2>${title}</h2><p>${sub}</p>
    <ol>${steps.map(([h, t]) => `<li><div>${h}<span>${t}</span></div></li>`).join("")}</ol>
    <button class="btn btn-primary btn-block btn-lg">${t("Tuşunarli")}</button></div>`;
  const close = () => { bg.remove(); try { localStorage.setItem("uzilmas_guide_" + key, "1"); } catch (e) {} };
  bg.querySelector("button").onclick = close; bg.onclick = e => { if (e.target === bg) close(); };
  document.body.appendChild(bg);
}
function helpButton(fn) {
  return `<button class="helpbtn" onclick="${fn}">${ic("help", 16)}<span>${t("Yöriqnoma")}</span></button>`;
}

// ---------- Telegram Mini App ----------
const TG = (window.Telegram && Telegram.WebApp && Telegram.WebApp.initData) ? Telegram.WebApp : null;
if (TG) {
  document.documentElement.classList.add("tg");
  try {
    TG.ready(); TG.expand();
    TG.setHeaderColor && TG.setHeaderColor("#FFFFFF");
    TG.setBackgroundColor && TG.setBackgroundColor("#F5F8FC");
    if (location.pathname !== "/app") {            // ichki sahifalarda Telegram "Orqaga" tugmasi
      TG.BackButton.show(); TG.BackButton.onClick(() => { location.href = "/app"; });
    }
  } catch (e) {}
}
function haptic(kind) { try { TG && TG.HapticFeedback.notificationOccurred(kind || "success"); } catch (e) {} }
