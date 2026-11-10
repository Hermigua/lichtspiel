/* Lichtspiel – Weboberfläche. Eigener Code ohne fremde Bibliotheken. */
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ico = n => `<svg class="ico"><use href="#i-${n}"/></svg>`;
const S = { state: null, user: null, prefs: {}, libs: [], ext: [] };

async function api(path, opts = {}) {
  const o = { method: opts.method || (opts.body !== undefined ? "POST" : "GET"), headers: {} };
  if (opts.body !== undefined) { o.headers["Content-Type"] = "application/json"; o.body = JSON.stringify(opts.body); }
  const r = await fetch(path, o);
  let j = null;
  try { j = await r.json(); } catch (e) { j = null; }
  if (r.status === 401 && !opts.noAuth) { showLogin(); throw new Error("Nicht angemeldet"); }
  if (!r.ok) throw new Error((j && j.error) || ("Fehler " + r.status));
  return j;
}
function toast(t, ms = 2600) {
  const e = $("#toast"); e.textContent = t; e.classList.remove("hidden");
  clearTimeout(toast._t); toast._t = setTimeout(() => e.classList.add("hidden"), ms);
}
function fmtT(s) {
  s = Math.max(0, Math.floor(s || 0)); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
  return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(x).padStart(2, "0");
}
function fmtDur(s) {
  s = Math.round((s || 0) / 60); if (!s) return "";
  return s >= 60 ? `${Math.floor(s / 60)} Std. ${s % 60} Min.` : `${s} Min.`;
}
function fmtSize(b) {
  if (!b) return ""; const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0;
  while (b >= 1024 && i < 4) { b /= 1024; i++; } return b.toFixed(i > 2 ? 1 : 0).replace(".", ",") + " " + u[i];
}
function fmtDate(ts) { return ts ? new Date(ts * 1000).toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" }) : ""; }
const LANGS = { deu: "Deutsch", ger: "Deutsch", de: "Deutsch", eng: "Englisch", en: "Englisch", fra: "Französisch", fre: "Französisch",
  spa: "Spanisch", ita: "Italienisch", jpn: "Japanisch", tur: "Türkisch", pol: "Polnisch", rus: "Russisch", nld: "Niederländisch",
  dut: "Niederländisch", swe: "Schwedisch", dan: "Dänisch", nor: "Norwegisch", fin: "Finnisch", por: "Portugiesisch", kor: "Koreanisch",
  chi: "Chinesisch", zho: "Chinesisch", und: "Unbekannt" };
const lang = l => LANGS[(l || "").toLowerCase()] || (l ? l.toUpperCase() : "Unbekannt");
const chText = c => ({ 1: "Mono", 2: "Stereo", 6: "5.1", 8: "7.1" }[c] || (c ? c + " Kan." : ""));
const codecName = c => ({ h264: "H.264", hevc: "HEVC", av1: "AV1", vp9: "VP9", mpeg4: "MPEG-4", aac: "AAC", ac3: "Dolby Digital",
  eac3: "Dolby Digital+", dts: "DTS", truehd: "TrueHD", mp3: "MP3", flac: "FLAC", opus: "Opus", subrip: "SRT", ass: "ASS",
  hdmv_pgs_subtitle: "PGS (Bild)", dvd_subtitle: "VobSub (Bild)", mov_text: "MP4-Text", webvtt: "WebVTT", srt: "SRT" }[c] || (c || "").toUpperCase());
const resName = v => !v || !v.height ? "" : v.width >= 3200 || v.height >= 2000 ? "4K" : v.width >= 1800 || v.height >= 1000 ? "1080p" :
  v.width >= 1200 || v.height >= 700 ? "720p" : v.height >= 560 ? "576p" : v.height + "p";
const img = (id, t, w) => `/api/img/${id}/${t}?w=${w}`;

/* ---------- Start / Anmeldung ---------- */
async function boot() {
  S.state = await api("/api/state", { noAuth: true });
  document.title = S.state.name || "Lichtspiel";
  if (S.state.setup) return showSetup();
  if (!S.state.user) return showLogin();
  S.user = S.state.user; S.prefs = S.state.prefs || {};
  await loadLibs();
  $("#login").classList.add("hidden"); $("#app").classList.remove("hidden");
  $("#srvName").textContent = S.state.name;
  renderUserBtn();
  route();
}
async function loadLibs() { S.libs = await api("/api/libraries"); renderNav(); }

function showSetup() {
  const L = $("#login"); $("#app").classList.add("hidden"); L.classList.remove("hidden");
  L.innerHTML = `<div class="box"><div class="brand"><img src="logo.svg" alt="">Lichtspiel</div>
    <h2>Willkommen!</h2><p style="color:var(--dim)">Lege das Administrator-Konto an.</p>
    <form id="sf"><input name="name" placeholder="Name" required autocomplete="username">
    <input name="password" type="password" placeholder="Passwort (mind. 3 Zeichen)" required autocomplete="new-password">
    <button class="btn pri big">Einrichten</button><div class="msg err hidden"></div></form></div>`;
  $("#sf").onsubmit = async e => {
    e.preventDefault(); const f = e.target;
    try { await api("/api/setup", { body: { name: f.name.value, password: f.password.value } }); boot(); }
    catch (x) { const m = $(".msg", f); m.textContent = x.message; m.classList.remove("hidden"); }
  };
}

async function showLogin() {
  closePlayer(true);
  const L = $("#login"); $("#app").classList.add("hidden"); L.classList.remove("hidden");
  let profs = [];
  try { profs = await api("/api/profiles", { noAuth: true }); } catch (e) { }
  L.innerHTML = `<div class="box"><div class="brand"><img src="logo.svg" alt="">${esc(S.state?.name || "Lichtspiel")}</div>
    <h2>Wer schaut?</h2><div class="profiles">${profs.map(p => `<button data-n="${esc(p.name)}" data-pw="${p.has_pw ? 1 : 0}">
    <div class="avatar" style="background:${esc(p.color)}">${esc(p.name[0].toUpperCase())}</div><div class="n">${esc(p.name)}</div></button>`).join("")}</div>
    <form id="lf" class="hidden"><input name="name" placeholder="Name" autocomplete="username">
    <input name="password" type="password" placeholder="Passwort" autocomplete="current-password">
    <button class="btn pri big">Anmelden</button><a href="#" id="lfBack" style="color:var(--dim)">Anderes Profil</a>
    <div class="msg err hidden"></div></form></div>`;
  const f = $("#lf");
  const login = async () => {
    try { await api("/api/login", { body: { name: f.name.value, password: f.password.value }, noAuth: true }); boot(); }
    catch (x) { const m = $(".msg", f); m.textContent = x.message; m.classList.remove("hidden"); }
  };
  $$(".profiles button", L).forEach(b => b.onclick = () => {
    f.name.value = b.dataset.n;
    if (b.dataset.pw === "0") { f.password.value = ""; return login(); }
    $(".profiles", L).classList.add("hidden"); f.classList.remove("hidden"); f.name.classList.add("hidden"); f.password.focus();
  });
  if (!profs.length) f.classList.remove("hidden");
  $("#lfBack").onclick = e => { e.preventDefault(); f.classList.add("hidden"); $(".profiles", L).classList.remove("hidden"); f.name.classList.remove("hidden"); };
  f.onsubmit = e => { e.preventDefault(); login(); };
}

function renderUserBtn() {
  const u = S.user;
  $("#userBtn").innerHTML = `<span class="avatar" style="background:${esc(u.color)}">${esc(u.name[0].toUpperCase())}</span>`;
  $("#userBtn").onclick = e => { e.stopPropagation(); $("#userMenu").classList.toggle("hidden"); };
  $("#userMenu").innerHTML = `<div style="padding:8px 12px;color:var(--dim)">${esc(u.name)}${u.admin ? " · Admin" : ""}</div>
    <a href="#/settings/wiedergabe">Einstellungen</a><a href="#/stats">Meine Statistik</a>
    <button id="swUser">Profil wechseln</button><button id="logout">Abmelden</button>`;
  $("#logout").onclick = async () => { await api("/api/logout", { body: {} }); S.user = null; showLogin(); };
  $("#swUser").onclick = async () => { await api("/api/logout", { body: {} }); S.user = null; showLogin(); };
}
document.addEventListener("click", () => $("#userMenu")?.classList.add("hidden"));

function renderNav() {
  const libIcon = l => l.kind === "movie" ? "film" : "tv";
  const libs = S.libs.filter(l => !l.hidden);
  let h = `<a href="#/" data-r="home">${ico("home")}Start</a><div class="sep"></div><div class="lbl">Bibliotheken</div>` +
    libs.map(l => `<a href="#/lib/${l.id}" data-r="lib/${l.id}">${ico(libIcon(l))}${esc(l.name)}</a>`).join("");
  const ext = S.ext.filter(x => x.nav && (!x.admin || S.user.admin));
  if (ext.length) h += `<div class="sep"></div>` + ext.map(x => `<a href="#/${x.route}" data-r="${x.route}">${ico(x.icon)}${esc(x.nav)}</a>`).join("");
  h += `<div class="sep"></div><a href="#/stats" data-r="stats">${ico("stats")}Statistik</a>
    <a href="#/settings/wiedergabe" data-r="settings">${ico("gear")}Einstellungen</a>`;
  $("#nav").innerHTML = h;
}
$("#menuBtn").onclick = e => { e.stopPropagation(); document.body.classList.toggle("menu"); };
$("#side").addEventListener("click", e => { if (e.target.closest("a")) document.body.classList.remove("menu"); });

let searchT;
$("#search").addEventListener("input", e => {
  clearTimeout(searchT);
  const q = e.target.value.trim();
  searchT = setTimeout(() => { if (q.length >= 2) location.hash = "#/search/" + encodeURIComponent(q); }, 350);
});

/* ---------- Router ---------- */
window.addEventListener("hashchange", route);
let routeSeq = 0;
async function route() {
  if (!S.user) return;
  const seq = ++routeSeq;
  const h = location.hash.replace(/^#\/?/, "");
  const [p, ...rest] = h.split("/");
  $$("#nav a").forEach(a => a.classList.toggle("on", a.dataset.r === (p === "lib" ? "lib/" + rest[0] : (p || "home"))));
  const v = $("#view");
  v.innerHTML = `<div style="color:var(--dim)">Lädt …</div>`;
  window.scrollTo(0, 0);
  try {
    if (!p) await viewHome(v, seq);
    else if (p === "lib") await viewLib(v, +rest[0], seq);
    else if (p === "item") await viewItem(v, +rest[0], seq);
    else if (p === "search") await viewSearch(v, decodeURIComponent(rest.join("/")), seq);
    else if (p === "person") await viewPerson(v, decodeURIComponent(rest.join("/")), seq);
    else if (p === "settings") await viewSettings(v, rest[0] || "wiedergabe", seq);
    else if (p === "stats") await viewStats(v, seq);
    else {
      const x = S.ext.find(x => x.route === p);
      if (x) await x.view(v, rest, seq); else v.innerHTML = "<p>Seite nicht gefunden.</p>";
    }
  } catch (e) { if (seq === routeSeq) v.innerHTML = `<div class="msg err">${esc(e.message)}</div>`; }
}

/* ---------- Karten ---------- */
function card(it, o = {}) {
  const wide = o.wide;
  let src, t = it.title, s = "";
  if (wide) src = it.kind === "episode" ? img(it.id, "thumb", 480) : img(it.id, "backdrop", 480);
  else src = it.kind === "episode" ? img(it.id, "cover", 300) : img(it.id, "poster", 300);
  if (it.kind === "episode") {
    t = it.show_title || it.title;
    s = `S${it.season} · F${it.episode} – ${esc(it.title)}`;
  } else if (it.kind === "season") { s = esc(it.show_title || ""); if (it.total !== undefined) s = `${it.total} Folgen`; }
  else s = it.year ? String(it.year) : "";
  if (o.rank) t = `${o.rank}. ${t}`;
  const dur = it.duration || 0;
  const bar = it.pos > 0 && dur ? `<div class="bar"><i style="width:${Math.min(100, it.pos / dur * 100)}%"></i></div>` : "";
  let badge = "";
  if (it.unwatched > 0) badge = `<span class="badge">${it.unwatched}</span>`;
  else if (it.watched || it.unwatched === 0 && it.total) badge = `<span class="badge ok">${ico("check")}</span>`;
  const hasImg = wide ? true : (it.kind === "episode" || it.has_poster || it.kind === "season");
  return `<a class="card${wide ? " wide" : ""}" href="#/item/${it.id}" data-id="${it.id}">
    <div class="pic">${hasImg ? `<img loading="lazy" src="${src}" alt="" onerror="this.remove()">` : ""}
    <div class="ph" style="z-index:-1">${esc(t)}</div>${badge}${bar}</div>
    <div class="t">${esc(t)}</div>${s ? `<div class="s">${s}</div>` : ""}</a>`;
}
function hubHtml(hub) {
  const more = hub.lib ? `<a href="#/lib/${hub.lib}">Alle anzeigen</a>` : "";
  return `<section class="hub"><h2>${esc(hub.title)}${more}</h2><div class="row">${hub.items.map(i => card(i, { wide: hub.wide })).join("")}</div></section>`;
}

/* ---------- Startseite ---------- */
async function viewHome(v, seq) {
  const j = await api("/api/home");
  if (seq !== routeSeq) return;
  if (!j.hubs.length) {
    v.innerHTML = `<div class="panel"><h3>Noch nichts zu sehen</h3><p>${S.user.admin ?
      `Lege unter <a href="#/settings/bibliotheken" style="color:var(--acc)">Einstellungen → Bibliotheken</a> deine Film- und Serienordner an.` :
      "Ein Administrator muss erst Bibliotheken anlegen."}</p></div>`;
    return;
  }
  v.innerHTML = j.hubs.map(hubHtml).join("");
}

/* ---------- Bibliothek ---------- */
const libState = {};
async function viewLib(v, id, seq) {
  const lib = S.libs.find(l => l.id === id);
  if (!lib) { v.innerHTML = "<p>Bibliothek nicht gefunden.</p>"; return; }
  const st = libState[id] = libState[id] || { sort: "title", genre: "", letter: "", unwatched: false };
  const genres = await api(`/api/lib/${id}/genres`);
  if (seq !== routeSeq) return;
  const letters = "#ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");
  v.innerHTML = `<div class="toolbar"><h1>${esc(lib.name)}</h1><span class="cnt" id="lcnt"></span><span style="flex:1"></span>
    <select id="lsort"><option value="title">Titel</option><option value="added">Zuletzt hinzugefügt</option><option value="year">Jahr</option>
    <option value="release">Erscheinungsdatum</option><option value="rating">Bewertung</option></select>
    <select id="lgenre"><option value="">Alle Genres</option>${genres.map(g => `<option>${esc(g.g)}</option>`).join("")}</select>
    <label style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="lunw"> Ungesehen</label></div>
    <div class="letters" id="lletters" style="margin-bottom:14px"><button data-l="">Alle</button>${letters.map(l => `<button data-l="${l}">${l}</button>`).join("")}</div>
    <div class="grid" id="lgrid"></div><div id="lmore" style="height:40px"></div>`;
  $("#lsort").value = st.sort; $("#lgenre").value = st.genre; $("#lunw").checked = st.unwatched;
  let off = 0, total = 0, busy = false;
  const load = async reset => {
    if (busy) return; busy = true;
    if (reset) { off = 0; $("#lgrid").innerHTML = ""; }
    const qs = new URLSearchParams({ sort: st.sort, genre: st.genre, offset: off, limit: 120, unwatched: st.unwatched ? 1 : 0 });
    if (st.letter && st.letter !== "#") qs.set("letter", st.letter);
    const j = await api(`/api/lib/${id}/items?` + qs);
    if (seq !== routeSeq) return;
    let items = j.items;
    if (st.letter === "#") items = items.filter(i => !/^[a-zäöü]/i.test(i.title.replace(/^(der|die|das|the|a|an|ein|eine) /i, "")));
    total = j.total; off += j.items.length;
    $("#lgrid").insertAdjacentHTML("beforeend", items.map(i => card(i)).join(""));
    $("#lcnt").textContent = `${total} ${lib.kind === "movie" ? "Filme" : "Serien"}`;
    busy = false;
  };
  $$("#lletters button").forEach(b => { b.classList.toggle("on", b.dataset.l === st.letter); b.onclick = () => {
    st.letter = b.dataset.l; $$("#lletters button").forEach(x => x.classList.toggle("on", x === b)); load(true); }; });
  $("#lsort").onchange = e => { st.sort = e.target.value; load(true); };
  $("#lgenre").onchange = e => { st.genre = e.target.value; load(true); };
  $("#lunw").onchange = e => { st.unwatched = e.target.checked; load(true); };
  const io = new IntersectionObserver(es => { if (es[0].isIntersecting && off < total) load(false); }, { rootMargin: "800px" });
  io.observe($("#lmore"));
  await load(true);
}

/* ---------- Detailseite ---------- */
async function viewItem(v, id, seq) {
  const it = await api(`/api/item/${id}`);
  if (seq !== routeSeq) return;
  const wide = it.kind === "episode";
  const posterSrc = wide ? img(it.id, "thumb", 720) : img(it.id, it.kind === "season" ? "poster" : "poster", 440);
  const meta = [];
  if (it.kind === "episode") meta.push(`Staffel ${it.season} · Folge ${it.episode}`);
  if (it.year) meta.push(it.year);
  if (it.aired && it.kind === "episode") meta.push(new Date(it.aired).toLocaleDateString("de-DE"));
  if (it.duration) meta.push(fmtDur(it.duration));
  if (it.mpaa) meta.push(`<span class="mpaa">${esc(it.mpaa)}</span>`);
  if (it.rating) meta.push(`<span class="star">★ ${(+it.rating).toFixed(1).replace(".", ",")}</span>`);
  if (it.kind === "show") meta.push(`${it.children.length} Staffel${it.children.length === 1 ? "" : "n"}`);
  if (it.media && it.media.video) meta.push(resName(it.media.video));
  let sub = "";
  if (it.kind === "episode" || it.kind === "season") sub = `<a class="sub" href="#/item/${it.show_id}" style="display:block">${esc(it.show_title || "")}</a>`;
  const playable = it.kind === "movie" || it.kind === "episode";
  const target = playable ? it : it.play;
  let playLbl = "Abspielen", playStart = 0;
  if (playable && it.pos > 0 && !it.watched) { playLbl = `Fortsetzen ab ${fmtT(it.pos)}`; playStart = it.pos; }
  if (!playable && it.play) {
    playLbl = (it.play.pos > 0 ? "Fortsetzen" : "Abspielen") + ` S${it.play.season}·F${it.play.episode}`;
    playStart = it.play.pos || 0;
  }
  const watched = playable ? it.watched : it.unwatched === 0;
  v.innerHTML = `<div class="hero"><div class="bd" style="background-image:url('${img(it.id, "backdrop", 1600)}')"></div>
    <img class="poster${wide ? " wide" : ""}" src="${posterSrc}" alt="" onerror="this.style.visibility='hidden'">
    <div class="info">${it.has_logo && it.kind !== "episode" && it.kind !== "season" ? `<img class="logo" src="${img(it.id, "logo", 840)}" alt="${esc(it.title)}" onerror="this.outerHTML='<h1>${esc(it.title).replace(/'/g, "")}</h1>'">` : `<h1>${esc(it.title)}</h1>`}
    ${sub}${it.orig_title && it.orig_title !== it.title ? `<div class="sub">${esc(it.orig_title)}</div>` : ""}
    <div class="meta">${meta.join("<span>·</span>")}</div>
    <div>${(it.genres || []).map(g => `<span class="chip">${esc(g)}</span>`).join("")}</div>
    <div class="actions">${target ? `<button class="btn pri big" id="bPlay">${ico("play")}${esc(playLbl)}</button>` : ""}
    ${playStart > 0 ? `<button class="btn big" id="bRestart">${ico("restart")}Von Anfang an</button>` : ""}
    <button class="btn big ${watched ? "on" : ""}" id="bWatched" title="Gesehen">${ico("check")}${watched ? "Gesehen" : "Als gesehen markieren"}</button>
    <button class="btn big ${it.fav ? "on" : ""}" id="bFav" title="Favorit">${ico("heart")}</button></div>
    ${it.tagline ? `<div class="tagline">${esc(it.tagline)}</div>` : ""}
    <div class="plot">${esc(it.plot || "")}</div></div></div><div id="ibody"></div>`;
  const tid = target && target.id;
  if (tid) {
    $("#bPlay").onclick = () => openPlayer(tid, { start: playStart });
    if ($("#bRestart")) $("#bRestart").onclick = () => openPlayer(tid, { start: 0 });
  }
  $("#bWatched").onclick = async () => { await api(`/api/watched/${it.id}`, { body: { watched: !watched } }); route(); };
  $("#bFav").onclick = async () => { await api(`/api/fav/${it.id}`, { body: { on: !it.fav } }); route(); };
  const body = $("#ibody");
  let h = "";
  if (it.kind === "show") h += `<div class="section"><h3>Staffeln</h3><div class="grid">${it.children.map(c => card(c)).join("")}</div></div>`;
  if (it.kind === "season") h += `<div class="section"><h3>${it.children.length} Folgen</h3><div class="eps">${it.children.map(e => epRow(e)).join("")}</div></div>`;
  if (it.kind === "episode" && (it.prev || it.next)) h += `<div class="actions">${it.prev ? `<a class="btn" href="#/item/${it.prev}">← Vorherige Folge</a>` : ""}
    ${it.next ? `<a class="btn" href="#/item/${it.next.id}">Nächste Folge: S${it.next.season}·F${it.next.episode} ${esc(it.next.title)} →</a>` : ""}
    <a class="btn" href="#/item/${it.parent_id}">Zur Staffel</a></div>`;
  const people = (it.people || []).filter(p => p.type === "actor");
  const crew = (it.people || []).filter(p => p.type !== "actor");
  if (people.length) h += `<div class="section"><h3>Besetzung</h3><div class="people">${people.map(p => `<a class="person" href="#/person/${encodeURIComponent(p.name)}">
    <div class="ph"><img loading="lazy" src="/api/actor?id=${it.kind === "episode" || it.kind === "season" ? it.show_id : it.id}&name=${encodeURIComponent(p.name)}&w=200" alt="" onerror="this.replaceWith(document.createTextNode('${esc(p.name[0])}'))"></div>
    <div class="n">${esc(p.name)}</div><div class="r">${esc(p.role)}</div></a>`).join("")}</div></div>`;
  if (crew.length) h += `<div class="section"><div class="tech">${crew.map(p => `<span>${p.type === "director" ? "Regie" : "Drehbuch"}</span><b><a href="#/person/${encodeURIComponent(p.name)}">${esc(p.name)}</a></b>`).join("")}${it.studio ? `<span>Studio</span><b>${esc(it.studio)}</b>` : ""}</div></div>`;
  if (it.media) h += techHtml(it.media);
  body.innerHTML = h;
  $$(".ep", body).forEach(e => {
    e.onclick = ev => {
      if (ev.target.closest(".mk")) return;
      const c = it.children.find(x => x.id === +e.dataset.id);
      openPlayer(c.id, { start: c.pos > 0 && !c.watched ? c.pos : 0 });
    };
    $(".mk", e).onclick = async () => {
      const c = it.children.find(x => x.id === +e.dataset.id);
      await api(`/api/watched/${c.id}`, { body: { watched: !c.watched } }); c.watched = !c.watched;
      $(".mk", e).classList.toggle("on", c.watched);
    };
  });
}
function epRow(e) {
  const bar = e.pos > 0 && e.duration ? `<div class="bar"><i style="width:${Math.min(100, e.pos / e.duration * 100)}%"></i></div>` : "";
  return `<div class="ep" tabindex="0" data-id="${e.id}"><div class="pic"><img loading="lazy" src="${img(e.id, "thumb", 480)}" alt="" onerror="this.remove()">${bar}</div>
    <div class="tx"><h4>${e.episode}. ${esc(e.title)}</h4><div class="d">${[e.aired ? new Date(e.aired).toLocaleDateString("de-DE") : "", fmtDur(e.duration)].filter(Boolean).join(" · ")}
    · <a href="#/item/${e.id}" onclick="event.stopPropagation()" style="color:var(--acc)">Details</a></div><p>${esc(e.plot || "")}</p></div>
    <button class="mk ${e.watched ? "on" : ""}" title="Gesehen">${ico("check")}</button></div>`;
}
function techHtml(m) {
  const rows = [];
  if (m.file) rows.push(["Datei", esc(m.file)]);
  if (m.video) rows.push(["Video", `${codecName(m.video.codec)} ${resName(m.video)} (${m.video.width}×${m.video.height})${m.video.hdr ? " HDR" : ""}`]);
  m.audio.forEach((a, i) => rows.push([i ? "" : "Ton", `${lang(a.lang)} · ${codecName(a.codec)} ${chText(a.channels)}${a.title ? " · " + esc(a.title) : ""}`]));
  const subs = m.subs.map(s => `${lang(s.lang)} (${codecName(s.codec)}${s.forced ? ", erzwungen" : ""})`)
    .concat(m.ext_subs.map(s => `${lang(s.lang)} (extern${s.forced ? ", erzwungen" : ""})`));
  if (subs.length) rows.push(["Untertitel", subs.map(esc).join(", ")]);
  if (m.bitrate) rows.push(["Datenrate", Math.round(m.bitrate / 1000).toLocaleString("de-DE") + " kbit/s"]);
  if (m.size) rows.push(["Größe", fmtSize(m.size)]);
  return `<div class="section"><h3>Technische Angaben</h3><div class="tech">${rows.map(r => `<span>${r[0]}</span><b>${r[1]}</b>`).join("")}</div></div>`;
}

/* ---------- Suche / Person ---------- */
async function viewSearch(v, q, seq) {
  $("#search").value = q;
  const j = await api(`/api/search?q=${encodeURIComponent(q)}`);
  if (seq !== routeSeq) return;
  const mv = j.items.filter(i => i.kind !== "episode"), ep = j.items.filter(i => i.kind === "episode");
  v.innerHTML = `<h1 style="margin-top:0">Suche: „${esc(q)}“</h1>` +
    (mv.length ? `<section class="hub"><h2>Filme & Serien</h2><div class="grid">${mv.map(i => card(i)).join("")}</div></section>` : "") +
    (ep.length ? `<section class="hub"><h2>Folgen</h2><div class="row">${ep.map(i => card(i, { wide: true })).join("")}</div></section>` : "") +
    (j.people.length ? `<section class="hub"><h2>Mit Personen namens „${esc(q)}“</h2><div class="row">${j.people.map(i => card(i)).join("")}</div></section>` : "") +
    (!mv.length && !ep.length && !j.people.length ? "<p>Nichts gefunden.</p>" : "");
}
async function viewPerson(v, name, seq) {
  const j = await api(`/api/person?name=${encodeURIComponent(name)}`);
  if (seq !== routeSeq) return;
  v.innerHTML = `<h1 style="margin-top:0">${esc(name)}</h1><div class="grid">${j.items.map(i => card(i)).join("")}</div>`;
}

/* ---------- Player ---------- */
const P = { info: null, offset: 0, cues: [], timer: null, uiT: null, lastRep: 0, fallback: 0 };
function detectCaps() {
  const v = document.createElement("video");
  const ok = t => { try { return (window.MediaSource && MediaSource.isTypeSupported(t)) || v.canPlayType(t) !== ""; } catch (e) { return false; } };
  const vc = [], ac = [], ct = ["mp4"];
  if (ok('video/mp4; codecs="avc1.640028"')) vc.push("h264");
  if (ok('video/mp4; codecs="hvc1.1.6.L120.90"') || ok('video/mp4; codecs="hev1.1.6.L120.90"')) vc.push("hevc");
  if (ok('video/webm; codecs="vp9"')) { vc.push("vp9"); ct.push("webm"); }
  if (ok('video/mp4; codecs="av01.0.08M.08"')) vc.push("av1");
  if (ok('audio/mp4; codecs="mp4a.40.2"')) ac.push("aac");
  if (ok("audio/mpeg")) ac.push("mp3");
  if (ok('audio/webm; codecs="opus"')) ac.push("opus");
  if (ok('audio/mp4; codecs="flac"') || ok("audio/flac")) ac.push("flac");
  if (ok('audio/mp4; codecs="ac-3"')) ac.push("ac3");
  if (ok('audio/mp4; codecs="ec-3"')) ac.push("eac3");
  if (ok('audio/webm; codecs="vorbis"')) ac.push("vorbis");
  return { vc, ac, ct };
}
const CAPS = detectCaps();

async function openPlayer(id, o = {}) {
  closePlayer(true);
  const el = $("#player");
  el.classList.remove("hidden"); el.classList.add("ui");
  el.innerHTML = `<video playsinline></video><div class="subs"></div><div class="center"><div class="spin"></div></div>
    <div class="ov"><div class="ptop"><div class="tt"><h2 id="pT"></h2><div class="st" id="pS"></div><div class="info" id="pI"></div></div>
    <button class="ibtn" id="pClose" title="Schließen (Esc)" style="background:none;border:0;color:#fff">${ico("close")}</button></div>
    <div class="pbot"><div class="seek" id="pSeek"><div class="tr"></div><div class="bf"></div><div class="pl"></div><div class="kn"></div><div class="tip hidden"></div></div>
    <div class="ctl"><button id="pBack" title="Zurück">${ico("back")}</button><button class="big" id="pPlay">${ico("pause")}</button>
    <button id="pFwd" title="Vor">${ico("fwd")}</button><button id="pNext" class="hidden" title="Nächste Folge">${ico("next")}</button>
    <span class="tm" id="pTm">0:00 / 0:00</span><span class="sp"></span><span class="end" id="pEnd"></span>
    <button id="pCh" class="hidden" title="Kapitel (K)">${ico("list")}</button><button id="pSpd" title="Tempo">${ico("speed")}</button>
    <button id="pSleep" title="Schlaf-Timer">${ico("moon")}</button>
    <button id="pAud" title="Ton">${ico("audio")}</button><button id="pSub" title="Untertitel">${ico("sub")}</button>
    <button id="pQ" title="Qualität">${ico("hq")}</button><button id="pFull" title="Vollbild (F)">${ico("full")}</button></div></div></div>
    <div class="pause-info"></div>`;
  const v = $("video", el);
  P.v = v; P.fallback = 0; P.closing = false; P.tv = o.tv || null; P.nuDismissed = false;
  v.addEventListener("waiting", () => $(".center", el).classList.remove("hidden"));
  v.addEventListener("playing", () => { $(".center", el).classList.add("hidden"); setPlayIcon(); });
  v.addEventListener("pause", () => { setPlayIcon(); report("paused"); showUi(); });
  v.addEventListener("play", setPlayIcon);
  v.addEventListener("ended", onEnded);
  v.addEventListener("error", onVideoError);
  v.addEventListener("timeupdate", tick);
  v.addEventListener("progress", tick);
  el.onmousemove = showUi;
  el.ontouchstart = showUi;
  v.onclick = () => togglePlay();
  v.ondblclick = () => toggleFull();
  $("#pClose").onclick = () => closePlayer();
  $("#pPlay").onclick = togglePlay;
  $("#pBack").onclick = () => seekTo(cur() - (S.prefs.skip_back || 10));
  $("#pFwd").onclick = () => seekTo(cur() + (S.prefs.skip_fwd || 30));
  $("#pFull").onclick = toggleFull;
  $("#pAud").onclick = e => { e.stopPropagation(); popMenu("aud"); };
  $("#pSub").onclick = e => { e.stopPropagation(); popMenu("sub"); };
  $("#pQ").onclick = e => { e.stopPropagation(); popMenu("q"); };
  $("#pCh").onclick = e => { e.stopPropagation(); popMenu("ch"); };
  $("#pSpd").onclick = e => { e.stopPropagation(); popMenu("spd"); };
  $("#pSleep").onclick = e => { e.stopPropagation(); popMenu("sleep"); };
  v.addEventListener("pause", () => { if (S.prefs.pause_info !== false && P.info && !P.live) { paintPause(); el.classList.add("paused"); } });
  v.addEventListener("play", () => el.classList.remove("paused"));
  $("#pNext").onclick = () => P.info.next && openPlayer(P.info.next.id, { start: 0 });
  setupSeek();
  P.timer = setInterval(() => { if (!v.paused) report("playing"); }, 10000);
  await startPlay(id, { start: o.start, audio: o.audio, sub: o.sub, height: o.height, force: o.force });
  if (P.tv) { $("#pNext").classList.add("hidden"); $("#pS").textContent = "📺 " + P.tv.name + " · " + $("#pS").textContent; }
}

async function startPlay(id, o) {
  const el = $("#player");
  let info;
  try {
    info = await api(`/api/play/${id}`, { body: { caps: CAPS, start: o.start, audio: o.audio, sub: o.sub, height: o.height, force: o.force } });
  } catch (e) { return playerError(e.message); }
  if (P.closing) return;
  P.info = info; P.id = id; P.height = o.height || null;
  $("#pT").textContent = info.kind === "episode" ? info.show_title : info.title;
  $("#pS").textContent = info.kind === "episode" ? `Staffel ${info.season} · Folge ${info.episode} – ${info.title}` : (info.year || "");
  $("#pNext").classList.toggle("hidden", !info.next);
  $("#pCh").classList.toggle("hidden", !(info.chapters || []).length);
  updInfoLine();
  setSrc(info.start || 0);
  loadSubs(info.sub_sel);
}
function updInfoLine() {
  const i = P.info, v = i.video || {};
  const mode = { direct: "Direkt", remux: "Remux", transcode: "Umgewandelt" }[i.mode.replace("*", "")];
  const a = (i.audio || []).find(x => x.i === i.audio_sel);
  $("#pI").textContent = [mode, v.codec ? codecName(v.codec) + " " + resName(v) : "", a ? `${lang(a.lang)} ${codecName(a.codec)} ${chText(a.channels)}` : "",
    P.height && i.mode === "transcode" ? `→ ${P.height}p` : "", i.bitrate ? Math.round(i.bitrate / 1000).toLocaleString("de-DE") + " kbit/s" : ""].filter(Boolean).join(" · ");
}
function setSrc(t) {
  const v = P.v, i = P.info;
  $(".center", $("#player")).classList.remove("hidden");
  if (i.mode === "direct") {
    P.offset = 0;
    v.src = i.url;
    const go = () => { if (t > 0) v.currentTime = t; v.playbackRate = P.rate || 1; v.play().catch(() => showUi()); };
    v.addEventListener("loadedmetadata", go, { once: true });
  } else {
    P.offset = t;
    v.src = i.url + "&t=" + t.toFixed(2);
    v.playbackRate = P.rate || 1;
    v.play().catch(() => showUi());
  }
}
const cur = () => P.offset + (P.v ? P.v.currentTime : 0);
const dur = () => (P.info && P.info.duration) || (P.v && isFinite(P.v.duration) ? P.v.duration : 0);
let seekT;
function seekTo(t) {
  t = Math.max(0, Math.min(t, dur() - 2));
  if (P.info.mode === "direct") { P.v.currentTime = t; return; }
  P.pendingSeek = t; tick();
  clearTimeout(seekT);
  seekT = setTimeout(() => { setSrc(t); P.pendingSeek = null; }, 350);
}
function togglePlay() { if (!P.v) return; if (P.v.paused) P.v.play(); else P.v.pause(); showUi(); }
function setPlayIcon() { if ($("#pPlay")) $("#pPlay").innerHTML = ico(P.v.paused ? "play" : "pause"); }
function toggleFull() {
  const el = $("#player");
  if (document.fullscreenElement) document.exitFullscreen();
  else if (el.requestFullscreen) el.requestFullscreen().catch(() => { });
  else if (P.v.webkitEnterFullscreen) P.v.webkitEnterFullscreen();
}
function showUi() {
  const el = $("#player"); el.classList.add("ui");
  clearTimeout(P.uiT);
  P.uiT = setTimeout(() => { if (P.v && !P.v.paused && !$(".pop", el)) el.classList.remove("ui"); }, 3200);
}
function tick() {
  if (!P.v || !P.info) return;
  const t = P.pendingSeek ?? cur(), d = dur();
  const pct = d ? t / d * 100 : 0;
  $("#pSeek .pl").style.width = pct + "%";
  $("#pSeek .kn").style.left = pct + "%";
  const b = P.v.buffered;
  if (b.length && d) $("#pSeek .bf").style.width = Math.min(100, (P.offset + b.end(b.length - 1)) / d * 100) + "%";
  $("#pTm").textContent = `${fmtT(t)} / ${fmtT(d)}`;
  const rest = (d - t) / (P.rate || 1), end = new Date(Date.now() + rest * 1000), rm = Math.max(0, Math.round(rest / 60));
  $("#pEnd").textContent = d ? `noch ${rm >= 60 ? Math.floor(rm / 60) + " Std. " + (rm % 60) + " Min." : rm + " Min."} · Ende ${end.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })}` +
    (P.sleep ? ` · ☾ ${P.sleep === "end" ? "nach diesem Titel" : fmtT((P.sleep - Date.now()) / 1000)}` : "") : "";
  if (P.sleep && P.sleep !== "end" && Date.now() >= P.sleep) { P.sleep = null; P.v.pause(); toast("Schlaf-Timer: angehalten", 4000); }
  renderSub(t);
  checkMarkers(t, d);
}
function setupSeek() {
  const s = $("#pSeek"), tip = $(".tip", s);
  const at = e => { const r = s.getBoundingClientRect(); return Math.max(0, Math.min(1, ((e.touches ? e.touches[0].clientX : e.clientX) - r.left) / r.width)) * dur(); };
  s.onmousemove = e => { const t = at(e); tip.textContent = fmtT(t); tip.style.left = (t / dur() * 100) + "%"; tip.classList.remove("hidden"); };
  s.onmouseleave = () => tip.classList.add("hidden");
  s.onclick = e => seekTo(at(e));
  // Markierungen (Intro/Abspann)
  setTimeout(() => (P.info?.chapters || []).forEach(c => {          // Kapitel als kleine Striche
    const d = dur(); if (!d || c.start < 1) return;
    const e = document.createElement("div"); e.className = "ch"; e.style.left = (c.start / d * 100) + "%"; s.appendChild(e);
  }), 1500);
  s.addEventListener("mousemove", e => { const ch = chapterAt(at(e)); if (ch && ch.title) tip.textContent += " · " + ch.title; });
  setTimeout(() => (P.info?.markers || []).forEach(m => {
    const d = dur(); if (!d) return;
    const e = document.createElement("div"); e.className = "mk";
    e.style.left = (m.start / d * 100) + "%"; e.style.width = (((m.end || d) - m.start) / d * 100) + "%";
    s.insertBefore(e, $(".pl", s));
  }), 1500);
}
function report(state) {
  if (!P.info || !P.v) return;
  const t = cur();
  if (state === "playing" && Math.abs(t - P.lastRep) < 1) return;
  P.lastRep = t;
  api("/api/progress", { body: { id: P.info.id, pos: t, dur: dur(), play: P.info.play, state, tv: !!P.tv } }).catch(() => { });
}
function onEnded() {
  report("stopped");
  if (P.sleep === "end") { P.sleep = null; toast("Schlaf-Timer: Ende des Titels", 4000); return closePlayer(); }
  if (P.tv && window.openChannel) return openChannel(P.tv.id);
  const n = P.info && P.info.next;
  if (n && S.prefs.autoplay !== false) openPlayer(n.id, { start: 0 });
  else closePlayer();
}
async function onVideoError() {
  if (!P.info || P.closing) return;
  const t = cur();
  if (P.info.mode === "direct" && P.fallback < 1) { P.fallback = 1; toast("Direktwiedergabe nicht möglich – Remux"); return startPlay(P.id, { start: t, audio: P.info.audio_sel, sub: P.info.sub_sel, force: "remux" }); }
  if (P.info.mode !== "transcode" && P.fallback < 2) { P.fallback = 2; toast("Wird umgewandelt …"); return startPlay(P.id, { start: t, audio: P.info.audio_sel, sub: P.info.sub_sel, force: "transcode", height: P.height }); }
  playerError("Wiedergabe fehlgeschlagen.");
}
function playerError(msg) {
  const el = $("#player"); $(".center", el)?.classList.add("hidden");
  el.insertAdjacentHTML("beforeend", `<div class="err"><h3>Wiedergabe nicht möglich</h3><p>${esc(msg)}</p><button class="btn" onclick="closePlayer()">Schließen</button></div>`);
}
function closePlayer(silent) {
  const el = $("#player");
  if (!el || el.classList.contains("hidden")) return;
  P.closing = true; P.live = null;
  if (!silent || P.info) report("stopped");
  clearInterval(P.timer); clearTimeout(P.uiT);
  if (P.v) { P.v.pause(); P.v.removeAttribute("src"); P.v.load(); }
  if (document.fullscreenElement) document.exitFullscreen().catch(() => { });
  el.classList.add("hidden"); el.innerHTML = "";
  const id = P.info && P.info.id;
  P.info = null; P.v = null; P.cues = []; P.sleep = null; P.rate = 1;
  if (!silent && id && location.hash.startsWith("#/item/")) route();
  else if (!silent && (!location.hash || location.hash === "#/")) route();
}
function popMenu(kind) {
  const el = $("#player"); const old = $(".pop", el);
  if (old) { old.remove(); if (old.dataset.k === kind) return; }
  const i = P.info; let h = "";
  if (kind === "aud") h = `<h4>Tonspur</h4>` + (i.audio || []).map(a => `<button data-a="${a.i}" class="${a.i === i.audio_sel ? "on" : ""}">${lang(a.lang)} · ${codecName(a.codec)} ${chText(a.channels)}${a.title ? " · " + esc(a.title) : ""}</button>`).join("");
  if (kind === "sub") h = `<h4>Untertitel</h4><button data-s="" class="${!i.sub_sel && i.burn == null ? "on" : ""}">Aus</button>` +
    (i.subs || []).map(s => `<button data-s="${s.key}" class="${s.key === i.sub_sel || (i.burn != null && s.key === "i" + i.burn) ? "on" : ""}">${lang(s.lang)}${s.forced ? " (erzwungen)" : ""} · ${codecName(s.codec)}${s.title && s.title !== "extern" ? " · " + esc(s.title) : ""}${s.title === "extern" ? " · extern" : ""}${s.text ? "" : " – wird eingebrannt"}</button>`).join("") +
    `<h4>Größe</h4>${[75, 100, 125, 150].map(z => `<button data-z="${z}" class="${(S.prefs.sub_size || 100) === z ? "on" : ""}">${z} %</button>`).join("")}`;
  if (kind === "q") h = `<h4>Qualität</h4>${[[0, "Original"], [1080, "1080p"], [720, "720p"], [480, "480p"], [360, "360p"]].map(([q, l]) =>
    `<button data-q="${q}" class="${(P.height || 0) === q ? "on" : ""}">${l}</button>`).join("")}<h4>Info</h4><div style="padding:4px 12px;font-size:13px;color:#94a3b8">${esc($("#pI").textContent)}</div>`;
  if (kind === "ch") { const now = chapterAt(cur());
    h = `<h4>Kapitel</h4>` + (i.chapters || []).map((c, n) => `<button data-ch="${n}" class="${c === now ? "on" : ""}">${fmtT(c.start)} · ${esc(c.title || "Kapitel " + (n + 1))}</button>`).join(""); }
  if (kind === "spd") h = `<h4>Tempo</h4>${[0.75, 1, 1.1, 1.25, 1.5, 2].map(r => `<button data-r="${r}" class="${(P.rate || 1) === r ? "on" : ""}">${r === 1 ? "Normal" : String(r).replace(".", ",") + "×"}</button>`).join("")}`;
  if (kind === "sleep") h = `<h4>Schlaf-Timer</h4><button data-sl="0" class="${!P.sleep ? "on" : ""}">Aus</button>${[15, 30, 45, 60, 90].map(m => `<button data-sl="${m}">${m} Minuten</button>`).join("")}
    <button data-sl="end" class="${P.sleep === "end" ? "on" : ""}">Nach diesem Titel</button>`;
  const pop = document.createElement("div"); pop.className = "pop"; pop.dataset.k = kind; pop.innerHTML = h;
  pop.onclick = e => {
    e.stopPropagation();
    const b = e.target.closest("button"); if (!b) return;
    const t = cur();
    if (b.dataset.a !== undefined) startPlay(P.id, { start: t, audio: +b.dataset.a, sub: i.sub_sel || (i.burn != null ? "i" + i.burn : ""), height: P.height });
    else if (b.dataset.s !== undefined) {
      const s = (i.subs || []).find(x => x.key === b.dataset.s);
      if (s && !s.text || i.burn != null) startPlay(P.id, { start: t, audio: i.audio_sel, sub: b.dataset.s, height: P.height });
      else { i.sub_sel = b.dataset.s || null; loadSubs(i.sub_sel); }
    } else if (b.dataset.z) { S.prefs.sub_size = +b.dataset.z; api("/api/me/prefs", { method: "PUT", body: { sub_size: S.prefs.sub_size } }); applySubStyle(); }
    else if (b.dataset.ch !== undefined) seekTo(i.chapters[+b.dataset.ch].start + 0.1);
    else if (b.dataset.r) { P.rate = +b.dataset.r; P.v.playbackRate = P.rate; toast("Tempo " + (P.rate === 1 ? "normal" : String(P.rate).replace(".", ",") + "×"), 1200); }
    else if (b.dataset.sl !== undefined) { const m = b.dataset.sl; P.sleep = m === "0" ? null : m === "end" ? "end" : Date.now() + +m * 60000;
      toast(P.sleep ? "Schlaf-Timer: " + (m === "end" ? "nach diesem Titel" : m + " Minuten") : "Schlaf-Timer aus", 1600); tick(); }
    else if (b.dataset.q !== undefined) startPlay(P.id, { start: t, audio: i.audio_sel, sub: i.sub_sel, height: +b.dataset.q || null, force: +b.dataset.q ? "transcode" : undefined });
    pop.remove();
  };
  el.appendChild(pop); showUi();
}
document.addEventListener("click", () => $("#player .pop")?.remove());

/* Kapitel und Pause-Ansicht */
function chapterAt(t) { const c = (P.info && P.info.chapters) || []; let r = null; for (const x of c) if (t >= x.start) r = x; return r; }
function paintPause() {
  const i = P.info, box = $("#player .pause-info"); if (!i || !box) return;
  const ch = chapterAt(cur());
  box.innerHTML = `${i.has_logo ? `<img src="${img(i.logo_id, "logo", 840)}" alt="" onerror="this.remove()">` : ""}
    <div class="badge2">PAUSE</div><h2>${esc(i.kind === "episode" ? i.show_title : i.title)}</h2>
    <div class="st">${i.kind === "episode" ? `Staffel ${i.season} · Folge ${i.episode} – ${esc(i.title)}` : esc(i.year || "")}${ch && ch.title ? ` · Kapitel: ${esc(ch.title)}` : ""}</div>
    ${i.plot ? `<p>${esc(i.plot)}</p>` : ""}`;
}

/* Untertitel: eigener VTT-Leser und eigene Darstellung */
function parseVtt(txt) {
  const cues = [], ts = s => { const p = s.trim().split(":").map(x => parseFloat(x.replace(",", "."))); return p.length === 3 ? p[0] * 3600 + p[1] * 60 + p[2] : p[0] * 60 + p[1]; };
  for (const block of txt.replace(/\r/g, "").split(/\n\n+/)) {
    const lines = block.split("\n"); const i = lines.findIndex(l => l.includes("-->"));
    if (i < 0) continue;
    const [a, b] = lines[i].split("-->");
    const text = lines.slice(i + 1).join("\n").replace(/<[^>]+>/g, "").replace(/\{\\[^}]*\}/g, "").trim();
    if (text) cues.push({ s: ts(a), e: ts(b.trim().split(" ")[0]), t: text });
  }
  return cues;
}
async function loadSubs(key) {
  P.cues = []; renderSub(0, true); applySubStyle();
  if (!key || !P.info) return;
  const id = P.info.id;
  try {
    const r = await fetch(`/api/sub/${id}/${key}.vtt`);
    if (!r.ok) throw new Error((await r.json()).error);
    if (!P.info || P.info.id !== id) return;
    P.cues = parseVtt(await r.text());
  } catch (e) { toast("Untertitel: " + e.message); }
}
function applySubStyle() {
  const s = $("#player .subs"); if (!s) return;
  s.style.setProperty("--ss", (S.prefs.sub_size || 100) / 100); s.classList.toggle("bg", !!S.prefs.sub_bg);
}
function renderSub(t, force) {
  const s = $("#player .subs"); if (!s) return;
  const c = P.cues.filter(c => t >= c.s && t <= c.e);
  const txt = c.map(x => x.t).join("\n");
  if (force || s.dataset.t !== txt) { s.dataset.t = txt; s.innerHTML = txt ? `<span>${esc(txt)}</span>` : ""; }
}
/* Intro überspringen / nächste Folge */
function checkMarkers(t, d) {
  const el = $("#player"); if (!el || !P.info) return;
  const intro = (P.info.markers || []).find(m => m.type === "intro" && t >= m.start && t < m.end - 1);
  let sk = $(".skipbtn", el);
  if (intro && !sk) {
    el.insertAdjacentHTML("beforeend", `<button class="btn pri big skipbtn">Intro überspringen</button>`);
    $(".skipbtn", el).onclick = () => seekTo(intro.end);
  } else if (!intro && sk) sk.remove();
  const n = P.tv ? null : P.info.next;
  const cred = (P.info.markers || []).find(m => m.type === "credits");
  const from = cred ? cred.start : d - 25;
  let nu = $(".nextup", el);
  if (n && d && t >= from && t < d - 1 && !P.nuDismissed) {
    if (!nu) {
      el.insertAdjacentHTML("beforeend", `<div class="nextup"><div style="color:#94a3b8;font-size:13px">Als Nächstes</div>
        <div style="font-weight:700;margin:4px 0 8px">S${n.season}·F${n.episode} – ${esc(n.title)}</div><img src="${img(n.id, "thumb", 480)}" alt="" onerror="this.remove()">
        <div class="actions" style="margin:10px 0 0"><button class="btn pri" id="nuGo">${ico("play")}Jetzt abspielen<span id="nuC"></span></button><button class="btn" id="nuNo">Abspann ansehen</button></div></div>`);
      $("#nuGo").onclick = () => { report("stopped"); openPlayer(n.id, { start: 0 }); };
      $("#nuNo").onclick = () => { P.nuDismissed = true; $(".nextup").remove(); };
      P.nuAt = Date.now();
    }
    if (S.prefs.autoplay !== false && cred) {
      const left = 15 - Math.floor((Date.now() - P.nuAt) / 1000);
      $("#nuC").textContent = ` (${Math.max(0, left)})`;
      if (left <= 0) { report("stopped"); openPlayer(n.id, { start: 0 }); }
    }
  } else if (nu && (t < from || P.nuDismissed)) nu.remove();
}
document.addEventListener("keydown", e => {
  if ($("#player").classList.contains("hidden") || !P.v || P.live || !P.info) return;
  if (e.target.tagName === "INPUT") return;
  const k = e.key;
  if (k === " " || k === "k") { e.preventDefault(); togglePlay(); }
  else if (k === "ArrowLeft") { e.preventDefault(); seekTo(cur() - (S.prefs.skip_back || 10)); showUi(); }
  else if (k === "ArrowRight") { e.preventDefault(); seekTo(cur() + (S.prefs.skip_fwd || 30)); showUi(); }
  else if (k === "ArrowUp") { e.preventDefault(); P.v.volume = Math.min(1, P.v.volume + .1); toast("Lautstärke " + Math.round(P.v.volume * 100) + " %", 900); }
  else if (k === "ArrowDown") { e.preventDefault(); P.v.volume = Math.max(0, P.v.volume - .1); toast("Lautstärke " + Math.round(P.v.volume * 100) + " %", 900); }
  else if (k === "f") toggleFull();
  else if ((k === "c" || k === "K") && (P.info.chapters || []).length) { e.preventDefault(); popMenu("ch"); }
  else if (k === "m") { P.v.muted = !P.v.muted; toast(P.v.muted ? "Stumm" : "Ton an", 900); }
  else if (k === "n" && P.info.next) openPlayer(P.info.next.id, { start: 0 });
  else if (k === "Escape" && !document.fullscreenElement) closePlayer();
});
window.addEventListener("beforeunload", () => {
  if (P.info && P.v) navigator.sendBeacon && fetch("/api/progress", { method: "POST", keepalive: true, headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: P.info.id, pos: cur(), dur: dur(), play: P.info.play, state: "stopped" }) });
});

/* ---------- Einstellungen ---------- */
const UNLICENSE = "This is free and unencumbered software released into the public domain.\n\nAnyone is free to copy, modify, publish, use, compile, sell, or\ndistribute this software, either in source code form or as a compiled\nbinary, for any purpose, commercial or non-commercial, and by any\nmeans.\n\nIn jurisdictions that recognize copyright laws, the author or authors\nof this software dedicate any and all copyright interest in the\nsoftware to the public domain. We make this dedication for the benefit\nof the public at large and to the detriment of our heirs and\nsuccessors. We intend this dedication to be an overt act of\nrelinquishment in perpetuity of all present and future rights to this\nsoftware under copyright law.\n\nTHE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND,\nEXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF\nMERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.\nIN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR\nOTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,\nARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR\nOTHER DEALINGS IN THE SOFTWARE.\n\nFor more information, please refer to <https://unlicense.org/>\n";
const SET_PAGES = [
  { id: "wiedergabe", t: "Wiedergabe" }, { id: "untertitel", t: "Untertitel" }, { id: "startseite", t: "Startseite & Menü" },
  { id: "anzeige", t: "Player & Bildschirmschoner" }, { id: "konto", t: "Konto" },
  { id: "bibliotheken", t: "Bibliotheken", admin: true, grp: "Server" }, { id: "benutzer", t: "Benutzer", admin: true },
  { id: "server", t: "Umwandlung & Scan", admin: true }, { id: "aktivitaet", t: "Aktivität", admin: true }, { id: "info", t: "Über & Lizenz" },
];
function seg(name, opts, valNow) {
  return `<div class="seg" data-seg="${name}">${opts.map(([v, l]) => `<button data-v='${JSON.stringify(v)}' class="${JSON.stringify(v) === JSON.stringify(valNow) ? "on" : ""}">${esc(l)}</button>`).join("")}</div>`;
}
function bindSegs(root, save) {
  $$(".seg", root).forEach(s => s.onclick = e => {
    const b = e.target.closest("button"); if (!b) return;
    $$("button", s).forEach(x => x.classList.toggle("on", x === b));
    save(s.dataset.seg, JSON.parse(b.dataset.v));
  });
}
async function savePref(k, v) {
  S.prefs = await api("/api/me/prefs", { method: "PUT", body: { [k]: v } }); toast("Gespeichert", 1000);
}
const LANG_OPTS = [["deu", "Deutsch"], ["eng", "Englisch"], ["fra", "Französisch"], ["spa", "Spanisch"], ["ita", "Italienisch"], ["jpn", "Japanisch"], ["tur", "Türkisch"]];
async function viewSettings(v, page, seq) {
  const pages = SET_PAGES.filter(p => !p.admin || S.user.admin).concat(S.ext.filter(x => x.settings && (!x.settingsAdmin || S.user.admin)).map(x => ({ id: x.settingsId, t: x.settings, admin: x.admin, ext: x })));
  let menu = "", grp = "Persönlich";
  menu += `<div class="lbl">Persönlich</div>`;
  for (const p of pages) {
    if (p.grp && p.grp !== grp) { grp = p.grp; menu += `<div class="lbl">${esc(grp)}</div>`; }
    menu += `<a href="#/settings/${p.id}" class="${p.id === page ? "on" : ""}">${esc(p.t)}</a>`;
  }
  v.innerHTML = `<div class="settings"><div class="menu">${menu}</div><div class="body" id="sbody"></div></div>`;
  const b = $("#sbody"), pr = S.prefs = await api("/api/me/prefs");
  if (seq !== routeSeq) return;
  const pg = pages.find(p => p.id === page);
  if (pg && pg.ext) return pg.ext.settingsView(b);
  if (page === "wiedergabe") {
    b.innerHTML = `<h2>Wiedergabe</h2><div class="panel">
      <div class="fr"><span class="l">Qualität</span>${seg("quality", [[0, "Original"], [1080, "1080p"], [720, "720p"], [480, "480p"]], pr.quality)}</div>
      <div class="fr"><span class="l">Direktwiedergabe</span>${seg("direct", [[true, "Erlaubt"], [false, "Immer umwandeln"]], pr.direct)}</div>
      <div class="fr"><span class="l">Bevorzugte Tonspur</span>${seg("audio_lang", LANG_OPTS, pr.audio_lang)}</div>
      <div class="fr"><span class="l">Nächste Folge automatisch</span>${seg("autoplay", [[true, "Ja"], [false, "Nein"]], pr.autoplay)}</div>
      <div class="fr"><span class="l">Zurückspringen</span>${seg("skip_back", [[5, "5 s"], [10, "10 s"], [15, "15 s"], [30, "30 s"]], pr.skip_back)}</div>
      <div class="fr"><span class="l">Vorspringen</span>${seg("skip_fwd", [[10, "10 s"], [15, "15 s"], [30, "30 s"], [60, "60 s"]], pr.skip_fwd)}</div></div>
      <p style="color:var(--dim)">Diese Einstellungen gelten für dein Profil im Browser und in der TV-App.</p>`;
    bindSegs(b, savePref);
  } else if (page === "untertitel") {
    b.innerHTML = `<h2>Untertitel</h2><div class="panel">
      <div class="fr"><span class="l">Automatisch einschalten</span>${seg("sub_mode", [["off", "Nie"], ["forced", "Nur erzwungene"], ["foreign", "Bei fremder Tonspur"], ["always", "Immer"]], pr.sub_mode)}</div>
      <div class="fr"><span class="l">Sprache</span>${seg("sub_lang", LANG_OPTS, pr.sub_lang)}</div>
      <div class="fr"><span class="l">Größe</span>${seg("sub_size", [[75, "Klein"], [100, "Normal"], [125, "Groß"], [150, "Sehr groß"]], pr.sub_size)}</div>
      <div class="fr"><span class="l">Hintergrund</span>${seg("sub_bg", [[0, "Ohne (Schatten)"], [1, "Dunkler Kasten"]], pr.sub_bg)}</div></div>`;
    bindSegs(b, savePref);
  } else if (page === "startseite") {
    await loadLibs();
    const draw = () => {
      const order = S.libs.map(l => l.id);
      b.innerHTML = `<h2>Startseite & Menü</h2><div class="panel"><h3>Bibliotheken – Reihenfolge und Sichtbarkeit</h3>
        <table class="tbl">${S.libs.map((l, i) => `<tr><td style="width:100%">${esc(l.name)}</td>
        <td><button class="btn sm" data-up="${i}" ${i ? "" : "disabled"}>↑</button></td><td><button class="btn sm" data-dn="${i}" ${i < S.libs.length - 1 ? "" : "disabled"}>↓</button></td>
        <td><button class="btn sm ${l.hidden ? "" : "on"}" data-h="${l.id}">${l.hidden ? "Ausgeblendet" : "Sichtbar"}</button></td></tr>`).join("")}</table></div>`;
      $$("[data-up],[data-dn]", b).forEach(x => x.onclick = async () => {
        const i = +(x.dataset.up ?? x.dataset.dn), j = x.dataset.up !== undefined ? i - 1 : i + 1;
        [order[i], order[j]] = [order[j], order[i]];
        await savePref("lib_order", order); await loadLibs(); draw();
      });
      $$("[data-h]", b).forEach(x => x.onclick = async () => {
        const id = +x.dataset.h, hid = new Set(S.prefs.lib_hidden || []);
        hid.has(id) ? hid.delete(id) : hid.add(id);
        await savePref("lib_hidden", [...hid]); await loadLibs(); draw();
      });
    };
    draw();
  } else if (page === "anzeige") {
    b.innerHTML = `<h2>Player & Bildschirmschoner</h2><div class="panel"><h3>Player</h3>
      <div class="fr"><span class="l">Pause-Ansicht</span>${seg("pause_info", [[true, "An"], [false, "Aus"]], pr.pause_info)}</div>
      <div class="fr hint">Bei Pause erscheinen Logo, Titel, Kapitel und Inhaltsangabe über dem Bild.</div></div>
      <div class="panel"><h3>Bildschirmschoner</h3>
      <div class="fr"><span class="l">Bildschirmschoner</span>${seg("saver_on", [[true, "An"], [false, "Aus"]], pr.saver_on)}</div>
      <div class="fr"><span class="l">Startet nach</span>${seg("saver_min", [[2, "2 Min."], [5, "5 Min."], [10, "10 Min."], [20, "20 Min."], [30, "30 Min."]], pr.saver_min)}</div>
      <div class="fr"><span class="l">Uhr anzeigen</span>${seg("saver_clock", [[true, "Ja"], [false, "Nein"]], pr.saver_clock)}</div>
      <div class="fr"><span class="l"></span><button class="btn" id="svTest">${ico("moon")}Jetzt testen</button></div>
      <div class="fr hint">Hintergrundbilder deiner Filme und Serien mit Uhr – nicht während eines laufenden Films oder Live-TV. Jede Taste oder Mausbewegung beendet ihn. Auch über den Mond-Knopf oben startbar.</div></div>`;
    bindSegs(b, savePref);
    $("#svTest").onclick = () => setTimeout(() => window.saverStart && saverStart(), 300);
  } else if (page === "konto") {
    b.innerHTML = `<h2>Konto</h2><div class="panel"><h3>Passwort ändern</h3><form id="pwf">
      <div class="fr"><label>Altes Passwort</label><input type="password" name="old" autocomplete="current-password"></div>
      <div class="fr"><label>Neues Passwort</label><input type="password" name="new" autocomplete="new-password"></div>
      <div class="fr"><span class="l"></span><button class="btn pri">Ändern</button></div></form>
      <p style="color:var(--dim)">Leeres neues Passwort = Anmeldung ohne Passwort (nicht für Administratoren).</p></div>`;
    $("#pwf").onsubmit = async e => { e.preventDefault(); try { await api("/api/me/password", { method: "PUT", body: { old: e.target.old.value, new: e.target.new.value } }); toast("Passwort geändert"); e.target.reset(); } catch (x) { toast(x.message); } };
  } else if (page === "bibliotheken" && S.user.admin) await setLibraries(b);
  else if (page === "benutzer" && S.user.admin) await setUsers(b);
  else if (page === "server" && S.user.admin) await setServer(b);
  else if (page === "aktivitaet" && S.user.admin) await setActivity(b, seq);
  else if (page === "info") b.innerHTML = `<h2>Über & Lizenz</h2><div class="panel"><p><b>Lichtspiel ${esc(S.state.version)}</b> – eigener Medienserver.</p>
    <p>Komplett selbst geschrieben und gemeinfrei (The Unlicense): frei nutzbar, veränderbar und weitergebbar – auch gewerblich.</p></div>
    <div class="panel"><h3>Fremde Bestandteile</h3><table class="tbl">
      <tr><td><b>Server</b></td><td>nur Python-Standardbibliothek und SQLite (gemeinfrei) – kein fremder Code</td></tr>
      <tr><td><b>Weboberfläche</b></td><td>eigenes HTML, CSS und JavaScript ohne Bibliotheken; Symbole selbst gezeichnet</td></tr>
      <tr><td><b>TV-App</b></td><td>reines Java gegen das Android-SDK – keine Zusatzbibliotheken im APK</td></tr>
      <tr><td><b>ffmpeg / ffprobe</b></td><td>wird <i>nicht</i> mitgeliefert, sondern als eigenständiges Programm des Servers aufgerufen (Medieninfos, Umwandlung, Standbilder). Es gilt die Lizenz der installierten Fassung (LGPL/GPL, <a href="https://ffmpeg.org/legal.html" target="_blank" rel="noopener" style="color:var(--acc)">ffmpeg.org/legal</a>).</td></tr></table></div>
    <div class="panel"><h3>Daten und Quellen</h3><p>Lichtspiel fragt keine Online-Dienste ab. Titel, Bilder und Beschreibungen stammen aus deinen eigenen Medienordnern (NFO und Bilder),
      Senderlisten und Programmdaten nur aus Quellen, die ein Administrator selbst einträgt. Für deren Inhalte (Streams, Logos, Programmdaten) gelten die Bedingungen der jeweiligen Anbieter.</p></div>
    <div class="panel"><h3>Lizenztext</h3><pre style="white-space:pre-wrap;font-size:13px;color:var(--dim)">${esc(UNLICENSE)}</pre></div>`;
  else b.innerHTML = "<p>Seite nicht gefunden.</p>";
}

async function setLibraries(b) {
  const libs = await api("/api/libraries");
  const sc = await api("/api/scan");
  b.innerHTML = `<h2>Bibliotheken</h2><div class="panel"><table class="tbl"><tr><th>Name</th><th>Art</th><th>Ordner</th><th>Einträge</th><th></th></tr>
    ${libs.map(l => `<tr><td><b>${esc(l.name)}</b></td><td>${l.kind === "movie" ? "Filme" : "Serien"}</td><td>${(l.paths || []).map(esc).join("<br>")}</td>
    <td>${l.count}<br><span style="color:var(--dim);font-size:12px">${l.scanned ? "Scan " + fmtDate(l.scanned) : "noch nicht gescannt"}</span></td>
    <td style="white-space:nowrap"><button class="btn sm" data-scan="${l.id}">Scannen</button> <button class="btn sm" data-edit="${l.id}">Bearbeiten</button> <button class="btn sm danger" data-del="${l.id}">Löschen</button></td></tr>`).join("")}</table>
    <div class="actions"><button class="btn pri" id="lnew">+ Bibliothek</button><button class="btn" id="lscan">Alle scannen</button><button class="btn" id="lfull">Alle neu einlesen (Metadaten)</button></div>
    <div id="lscanst" class="msg"></div></div><div id="lform"></div>`;
  const st = () => api("/api/scan").then(s => { const e = $("#lscanst"); if (!e) return; e.innerHTML = (s.running ? `Scan läuft: <b>${esc(s.lib)}</b> – ${s.done} Dateien geprüft` : "Kein Scan aktiv") +
    ` · Medieninfos ausstehend: ${s.unprobed}<br><span style="color:var(--dim);font-size:13px">${s.log.slice(-5).map(esc).join("<br>")}</span>`; if (s.running || s.unprobed) setTimeout(st, 3000); });
  st();
  $$("[data-scan]", b).forEach(x => x.onclick = async () => { await api(`/api/scan/${x.dataset.scan}`, { body: {} }); toast("Scan gestartet"); st(); });
  $("#lscan").onclick = async () => { await api("/api/scan", { body: {} }); toast("Scan gestartet"); st(); };
  $("#lfull").onclick = async () => { await api("/api/scan", { body: { full: true } }); toast("Vollständiges Einlesen gestartet"); st(); };
  $$("[data-del]", b).forEach(x => x.onclick = async () => {
    const l = libs.find(y => y.id === +x.dataset.del);
    if (!confirm(`Bibliothek „${l.name}“ entfernen? (Die Dateien bleiben unberührt.)`)) return;
    await api(`/api/libraries/${l.id}`, { method: "DELETE" }); await loadLibs(); setLibraries(b);
  });
  const form = l => {
    const paths = l ? [...l.paths] : [];
    const f = $("#lform");
    const draw = () => {
      f.innerHTML = `<div class="panel"><h3>${l ? "Bibliothek bearbeiten" : "Neue Bibliothek"}</h3>
      <div class="fr"><label>Name</label><input type="text" id="fn" value="${esc(l ? l.name : "")}"></div>
      ${l ? "" : `<div class="fr"><span class="l">Art</span>${seg("kind", [["movie", "Filme"], ["show", "Serien"]], "movie")}</div>`}
      <div class="fr"><span class="l">Ordner</span><div style="flex:1">${paths.map((p, i) => `<div style="display:flex;gap:8px;align-items:center;margin-bottom:4px"><code style="flex:1">${esc(p)}</code><button class="btn sm danger" data-rm="${i}">×</button></div>`).join("") || "<span style='color:var(--dim)'>noch keiner</span>"}</div></div>
      <div class="fr"><span class="l">Ordner wählen</span><div style="flex:1"><div style="display:flex;gap:8px"><input type="text" id="fpath" style="flex:1" value="/mount">
      <button class="btn" id="fadd">Hinzufügen</button></div><div class="dirpick" id="fpick"></div></div></div>
      <div class="actions"><button class="btn pri" id="fsave">Speichern</button><button class="btn" id="fcancel">Abbrechen</button></div></div>`;
      let kind = "movie";
      bindSegs(f, (k, v) => { kind = v; });
      const pick = async p => {
        try { const d = await api(`/api/dirs?path=${encodeURIComponent(p)}`); $("#fpath").value = d.path;
          $("#fpick").innerHTML = (d.parent ? `<div data-p="${esc(d.parent)}">⬑ ..</div>` : "") + d.dirs.map(x => `<div data-p="${esc((d.path === "/" ? "" : d.path) + "/" + x)}">📁 ${esc(x)}</div>`).join("");
          $$("#fpick div").forEach(x => x.onclick = () => pick(x.dataset.p));
        } catch (e) { toast(e.message); }
      };
      pick($("#fpath").value);
      $("#fpath").onchange = e => pick(e.target.value);
      $("#fadd").onclick = () => { const p = $("#fpath").value.trim(); if (p && !paths.includes(p)) { paths.push(p); const n = $("#fn").value; draw(); $("#fn").value = n; } };
      $$("[data-rm]", f).forEach(x => x.onclick = () => { paths.splice(+x.dataset.rm, 1); draw(); });
      $("#fcancel").onclick = () => f.innerHTML = "";
      $("#fsave").onclick = async () => {
        try {
          if (l) await api(`/api/libraries/${l.id}`, { method: "PUT", body: { name: $("#fn").value, paths } });
          else await api("/api/libraries", { body: { name: $("#fn").value, kind, paths } });
          toast("Gespeichert – Scan läuft"); await loadLibs(); setLibraries(b);
        } catch (e) { toast(e.message); }
      };
      f.scrollIntoView({ behavior: "smooth" });
    };
    draw();
  };
  $("#lnew").onclick = () => form(null);
  $$("[data-edit]", b).forEach(x => x.onclick = () => form(libs.find(y => y.id === +x.dataset.edit)));
}

async function setUsers(b) {
  const [users, libs] = await Promise.all([api("/api/users"), api("/api/libraries")]);
  b.innerHTML = `<h2>Benutzer</h2><div class="panel"><table class="tbl"><tr><th></th><th>Name</th><th>Rolle</th><th>Bibliotheken</th><th></th></tr>
    ${users.map(u => `<tr><td><span class="avatar" style="background:${esc(u.color)}">${esc(u.name[0].toUpperCase())}</span></td><td><b>${esc(u.name)}</b>${u.has_pw ? "" : "<br><span style='color:var(--dim);font-size:12px'>ohne Passwort</span>"}</td>
    <td>${u.admin ? "Administrator" : "Benutzer"}</td><td>${u.libs === null ? "Alle" : libs.filter(l => u.libs.includes(l.id)).map(l => esc(l.name)).join(", ") || "Keine"}</td>
    <td style="white-space:nowrap"><button class="btn sm" data-ed="${u.id}">Bearbeiten</button></td></tr>`).join("")}</table>
    <div class="actions"><button class="btn pri" id="unew">+ Benutzer</button></div></div><div id="uform"></div>`;
  const form = u => {
    const f = $("#uform");
    const sel = new Set(u && u.libs ? u.libs : []);
    let all = !u || u.libs === null, admin = u ? u.admin : false;
    f.innerHTML = `<div class="panel"><h3>${u ? "Benutzer bearbeiten" : "Neuer Benutzer"}</h3>
      <div class="fr"><label>Name</label><input type="text" id="un" value="${esc(u ? u.name : "")}"></div>
      <div class="fr"><label>${u ? "Neues Passwort" : "Passwort"}</label><input type="password" id="up" placeholder="${u ? "unverändert lassen = leer" : "leer = ohne Passwort"}" autocomplete="new-password">
      ${u ? `<label><input type="checkbox" id="upclr"> Passwort entfernen</label>` : ""}</div>
      <div class="fr"><span class="l">Rolle</span>${seg("admin", [[false, "Benutzer"], [true, "Administrator"]], admin)}</div>
      <div class="fr"><span class="l">Bibliotheken</span>${seg("all", [[true, "Alle"], [false, "Auswahl"]], all)}
      <div id="ulibs" class="${all ? "hidden" : ""}" style="width:100%;padding-left:244px">${libs.map(l => `<label style="display:block"><input type="checkbox" value="${l.id}" ${sel.has(l.id) ? "checked" : ""}> ${esc(l.name)}</label>`).join("")}</div></div>
      <div class="actions"><button class="btn pri" id="usave">Speichern</button><button class="btn" id="ucancel">Abbrechen</button>
      ${u && u.id !== S.user.id ? `<button class="btn danger" id="udel">Löschen</button>` : ""}</div></div>`;
    bindSegs(f, (k, v) => { if (k === "admin") admin = v; if (k === "all") { all = v; $("#ulibs").classList.toggle("hidden", v); } });
    $("#ucancel").onclick = () => f.innerHTML = "";
    if ($("#udel")) $("#udel").onclick = async () => { if (!confirm(`„${u.name}“ wirklich löschen? Verlauf und Fortschritt gehen verloren.`)) return; await api(`/api/users/${u.id}`, { method: "DELETE" }); setUsers(b); };
    $("#usave").onclick = async () => {
      const libsSel = all ? null : $$("#ulibs input:checked").map(x => +x.value);
      const body = { name: $("#un").value, admin, libs: libsSel };
      const pw = $("#up").value;
      if (!u || pw) body.password = pw;
      if (u && $("#upclr")?.checked) body.password = "";
      try { if (u) await api(`/api/users/${u.id}`, { method: "PUT", body }); else await api("/api/users", { body }); toast("Gespeichert"); setUsers(b); }
      catch (e) { toast(e.message); }
    };
    f.scrollIntoView({ behavior: "smooth" });
  };
  $("#unew").onclick = () => form(null);
  $$("[data-ed]", b).forEach(x => x.onclick = () => form(users.find(u => u.id === +x.dataset.ed)));
}

async function setServer(b) {
  const s = await api("/api/settings");
  const save = async (k, v) => { await api("/api/settings", { method: "PUT", body: { [k]: v } }); toast("Gespeichert", 1000); if (k === "server_name") { S.state.name = v; $("#srvName").textContent = v; } };
  b.innerHTML = `<h2>Umwandlung & Scan</h2><div class="panel"><h3>Allgemein</h3>
    <div class="fr"><label>Servername</label><input type="text" id="sname" value="${esc(s.server_name)}"></div></div>
    <div class="panel"><h3>Umwandlung (ffmpeg)</h3>
    <div class="fr"><span class="l">Geschwindigkeit</span>${seg("transcode_preset", [["ultrafast", "Sehr schnell"], ["veryfast", "Schnell"], ["faster", "Mittel"], ["medium", "Beste Qualität"]], s.transcode_preset)}</div>
    <div class="fr"><span class="l">Bildqualität (CRF)</span>${seg("transcode_crf", [[18, "18 sehr hoch"], [21, "21 hoch"], [23, "23 mittel"], [26, "26 sparsam"]], s.transcode_crf)}</div>
    <div class="fr"><span class="l">Prozessorkerne</span>${seg("transcode_threads", [[0, "Automatisch"], [2, "2"], [4, "4"], [8, "8"]], s.transcode_threads)}</div></div>
    <div class="panel"><h3>Gesehen & Fortsetzen</h3>
    <div class="fr"><span class="l">Gilt als gesehen ab</span>${seg("played_pct", [[85, "85 %"], [90, "90 %"], [95, "95 %"]], s.played_pct)}</div>
    <div class="fr"><span class="l">Fortsetzen erst ab</span>${seg("resume_min_s", [[30, "30 s"], [60, "1 Min."], [180, "3 Min."], [300, "5 Min."]], s.resume_min_s)}</div></div>
    <div class="panel"><h3>Bibliotheks-Scan</h3>
    <div class="fr"><span class="l">Automatisch scannen</span>${seg("scan_interval_h", [[0, "Aus"], [1, "Stündlich"], [6, "Alle 6 Std."], [24, "Täglich"]], s.scan_interval_h)}</div>
    <div class="fr"><span class="l">Medieninfo parallel</span>${seg("probe_workers", [[1, "1"], [2, "2"], [4, "4"]], s.probe_workers)}</div></div>`;
  bindSegs(b, save);
  $("#sname").onchange = e => save("server_name", e.target.value.trim() || "Lichtspiel");
}

async function setActivity(b, seq) {
  const draw = async () => {
    if (seq !== routeSeq || !document.body.contains(b)) return;
    const a = await api("/api/activity");
    b.innerHTML = `<h2>Aktivität</h2><div class="panel">${a.length ? `<table class="tbl"><tr><th>Benutzer</th><th>Titel</th><th>Art</th><th>Gerät</th><th>Position</th></tr>
      ${a.map(x => `<tr><td><span class="avatar" style="background:${esc(x.color)};width:26px;height:26px;font-size:13px">${esc(x.user[0])}</span> ${esc(x.user)}</td>
      <td><a href="#/item/${x.item}">${esc(x.title)}</a></td><td>${({ direct: "Direkt", remux: "Remux", transcode: "Umwandlung", live: "Live" })[x.mode] || esc(x.mode)}</td>
      <td>${esc(x.client)}</td><td>${fmtT(x.pos)}</td></tr>`).join("")}</table>` : "Gerade schaut niemand."}</div>`;
    setTimeout(draw, 5000);
  };
  draw();
}

/* ---------- Statistik ---------- */
let statDays = 30;
async function viewStats(v, seq) {
  const s = await api(`/api/stats?days=${statDays}`);
  if (seq !== routeSeq) return;
  const hrs = x => (x / 3600).toFixed(x >= 36000 ? 0 : 1).replace(".", ",") + " Std.";
  const hb = (rows, label, valF, link) => { const mx = Math.max(1, ...rows.map(valF)); return rows.map(r => `<div class="hbar"><span class="n">${link ? `<a href="${link(r)}">${label(r)}</a>` : label(r)}</span><span class="b"><i style="width:${valF(r) / mx * 100}%"></i></span><span class="c">${valF(r)}</span></div>`).join("") || "<span style='color:var(--dim)'>Noch keine Daten</span>"; };
  const days = [];
  for (let i = s.days - 1; i >= 0; i--) { const d = new Date(Date.now() - i * 86400000); days.push(d.toISOString().slice(0, 10)); }
  const dmap = Object.fromEntries(s.daily.map(d => [d.d, d.secs]));
  const dmx = Math.max(1, ...s.daily.map(d => d.secs));
  const hmap = Object.fromEntries(s.hours.map(h => [h.h, h.plays])); const hmx = Math.max(1, ...s.hours.map(h => h.plays));
  const wd = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"], wmap = Object.fromEntries(s.weekdays.map(w => [w.w, w.plays])); const wmx = Math.max(1, ...s.weekdays.map(w => w.plays));
  const mode = Object.fromEntries(s.modes.map(m => [m.mode, m.plays]));
  v.innerHTML = `<div class="toolbar"><h1>${S.user.admin ? "Statistik" : "Meine Statistik"}</h1><span style="flex:1"></span>${seg("days", [[7, "7 Tage"], [30, "30 Tage"], [90, "90 Tage"], [365, "1 Jahr"]], statDays)}</div>
    <div class="kpis"><div class="kpi"><div class="v">${s.total.plays}</div><div class="l">Wiedergaben</div></div>
    <div class="kpi"><div class="v">${hrs(s.total.secs)}</div><div class="l">Geschaut</div></div>
    <div class="kpi"><div class="v">${mode.direct || 0} / ${mode.remux || 0} / ${mode.transcode || 0}</div><div class="l">Direkt / Remux / Umgewandelt</div></div>
    ${S.user.admin ? `<div class="kpi"><div class="v">${s.users.length}</div><div class="l">Aktive Benutzer</div></div>` : ""}</div>
    <div class="panel"><h3>Geschaute Zeit pro Tag</h3><div class="bars">${days.map(d => `<div title="${d}: ${hrs(dmap[d] || 0)}" style="height:${(dmap[d] || 0) / dmx * 100}%"></div>`).join("")}</div>
    <div class="bars-l">${days.map((d, i) => `<span>${i % Math.ceil(days.length / 10) === 0 ? d.slice(8, 10) + "." + d.slice(5, 7) + "." : ""}</span>`).join("")}</div></div>
    <div class="two"><div class="panel"><h3>Tageszeit</h3><div class="bars" style="height:110px">${Array.from({ length: 24 }, (_, h) => `<div title="${h} Uhr: ${hmap[h] || 0}" style="height:${(hmap[h] || 0) / hmx * 100}%"></div>`).join("")}</div>
    <div class="bars-l">${Array.from({ length: 24 }, (_, h) => `<span>${h % 3 ? "" : h}</span>`).join("")}</div></div>
    <div class="panel"><h3>Wochentag</h3><div class="bars" style="height:110px">${[1, 2, 3, 4, 5, 6, 0].map(w => `<div title="${wd[w]}: ${wmap[w] || 0}" style="height:${(wmap[w] || 0) / wmx * 100}%"></div>`).join("")}</div>
    <div class="bars-l">${[1, 2, 3, 4, 5, 6, 0].map(w => `<span>${wd[w]}</span>`).join("")}</div></div></div>
    <div class="two"><div class="panel"><h3>Meistgesehene Filme</h3>${hb(s.top_movies, r => esc(r.title) + (r.year ? ` (${r.year})` : ""), r => r.plays, r => "#/item/" + r.id)}</div>
    <div class="panel"><h3>Meistgesehene Serien</h3>${hb(s.top_shows, r => esc(r.title), r => r.plays, r => "#/item/" + r.id)}</div></div>
    <div class="two"><div class="panel"><h3>Genres</h3>${hb(s.genres, r => esc(r.genre), r => r.plays)}</div>
    ${S.user.admin ? `<div class="panel"><h3>Benutzer</h3>${hb(s.users, r => esc(r.name), r => Math.round(r.secs / 3600))}<div style="color:var(--dim);font-size:12px">in Stunden</div></div>` :
      `<div class="panel"><h3>Bibliotheken</h3>${s.libraries.map(l => `<div class="hbar"><span class="n">${esc(l.name)}</span><span class="c" style="width:auto">${l.files} Dateien · ${fmtSize(l.bytes)}</span></div>`).join("")}</div>`}</div>
    ${S.user.admin ? `<div class="panel"><h3>Bibliotheken</h3><table class="tbl"><tr><th>Name</th><th>Dateien</th><th>Größe</th><th>Laufzeit</th></tr>${s.libraries.map(l => `<tr><td>${esc(l.name)}</td><td>${l.files}</td><td>${fmtSize(l.bytes)}</td><td>${hrs(l.secs)}</td></tr>`).join("")}</table></div>` : ""}
    <div class="panel"><h3>Verlauf</h3><table class="tbl"><tr><th>Zeit</th>${S.user.admin ? "<th>Benutzer</th>" : ""}<th>Titel</th><th>Dauer</th><th>Art</th><th>Gerät</th></tr>
    ${s.history.map(r => `<tr><td style="white-space:nowrap">${fmtDate(r.started)}</td>${S.user.admin ? `<td>${esc(r.user)}</td>` : ""}<td><a href="#/item/${r.item_id}">${esc(r.title)}</a></td>
    <td>${fmtT(r.seconds)}</td><td>${({ direct: "Direkt", remux: "Remux", transcode: "Umgewandelt", live: "Live" })[r.mode] || esc(r.mode)}</td><td>${esc(r.client)}</td></tr>`).join("")}</table></div>`;
  bindSegs(v, (k, d) => { statDays = d; route(); });
}

boot().catch(e => { document.body.innerHTML = `<p style="padding:20px">Fehler: ${esc(e.message)}</p>`; });
