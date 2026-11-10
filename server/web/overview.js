/* Lichtspiel – Senderübersicht (Live-TV und eigene Sender), Favoriten-Schnellzugriff, Bildschirmschoner. Eigener Code. */
"use strict";

/* ---------- Hilfen ---------- */
const ovNorm = s => String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").trim();
function ovLeft(p, now = Date.now() / 1000) {
  const m = Math.max(1, Math.round((p.stop - now) / 60));
  return m >= 60 ? `noch ${Math.floor(m / 60)} Std. ${m % 60} Min.` : `noch ${m} Min.`;
}
const ovShort = n => { n = String(n || "").trim(); if (n.length <= 6) return n;          // Kürzel fürs Logo-Kästchen (der volle Name steht daneben)
  const w = n.split(/[\s\-_.]+/).filter(Boolean), d = (n.match(/\d+/) || [""])[0];
  return (w.length > 1 ? w.slice(0, 3).map(x => x[0]).join("") : n.slice(0, 3)).toUpperCase() + (d && !w.slice(0, 3).some(x => /^\d/.test(x)) ? d : ""); };
const ovPct = p => p ? Math.max(0, Math.min(100, (Date.now() / 1000 - p.start) / (p.stop - p.start) * 100)) : 0;
const ovTick = () => Math.floor(Date.now() / 300000);           // Standbilder: alle 5 Minuten neue Adresse
async function ovFav(key, id) {                                  // Herz umschalten, gespeichert je Profil
  const l = (S.prefs[key] || []).slice(), i = l.indexOf(id);
  if (i >= 0) l.splice(i, 1); else l.push(id);
  S.prefs[key] = l;
  try { S.prefs = await api("/api/me/prefs", { method: "PUT", body: { [key]: l } }); } catch (e) { toast(e.message); }
  toast(i >= 0 ? "Aus den Favoriten entfernt" : "Zu den Favoriten hinzugefügt", 1400);
  return i < 0;
}

/* ---------- Senderübersicht ----------
   Oben die Bühne (zufälliger Sender, alle 5 s der nächste – Pause, solange die Maus darauf ist oder gesucht wird),
   darunter Suche, Sprungmarken (Favoriten, Gruppen) und je Gruppe die Sender als Zeilen:
   Standbild · Logo und Name · laufende Sendung mit Fortschritt · Danach · Knöpfe. */
const OVK = {
  live: { title: "Live-TV", list: "/api/live", fav: "live_favs", logo: c => `/api/live/${c.id}/logo`, snap: c => `/api/live/${c.id}/snap?t=${ovTick()}`,
    play: (c, list) => openLive(c.id, list), prog: "#/guide", progLbl: "Programmführer", searchPh: "Sender oder Sendung suchen",
    empty: () => `Keine Sender. ${S.user.admin ? `Senderlisten (M3U/M3U8) unter <a href="#/settings/live">Einstellungen → Live-TV</a> eintragen.` : ""}` },
  chan: { title: "Sender", list: "/api/channels", fav: "ch_favs", logo: c => `/api/channels/${c.id}/logo`, snap: null,
    play: c => openChannel(c.id), prog: null, progLbl: "Programm", searchPh: "Sender oder Titel suchen",
    empty: () => `Noch keine eigenen Sender. ${S.user.admin ? `Unter <a href="#/settings/sender">Einstellungen → Eigene Sender</a> anlegen.` : ""}` },
};
async function viewOverview(v, kind, seq) {
  const K = OVK[kind];
  let list = await api(K.list);
  if (seq !== routeSeq) return;
  if (kind === "chan") list = list.filter(c => c.enabled && c.count);
  const tok = v._ov = {};
  let q = "", heroId = null, hold = false;
  const withNow = () => { const l = list.filter(c => c.now); return l.length ? l : list; };
  if (list.length) heroId = withNow()[Math.floor(Math.random() * withNow().length)].id;
  const favs = () => (S.prefs[K.fav] || []).map(id => list.find(c => c.id === id)).filter(Boolean);
  const hit = c => { if (!q) return true; const t = ovNorm(q);
    return [c.name, c.group, c.now && c.now.title, c.now && c.now.sub, c.next && c.next.title].some(x => ovNorm(x).includes(t)); };
  const badge = (c, big) => c.has_logo ? `<span class="ovlogo${big ? " big" : ""}"><img src="${K.logo(c)}" alt="" onerror="this.parentNode.textContent=${esc(JSON.stringify(c.name))}"></span>`
    : `<span class="ovlogo${big ? " big" : ""} txt">${esc(ovShort(c.name))}</span>`;
  const pic = (c, cls) => kind === "live" ? `<span class="${cls}"><img src="${K.snap(c)}" alt="" loading="lazy" onerror="this.remove()"></span>`
    : `<span class="${cls}">${c.now && c.now.id ? `<img src="${img(c.now.id, "backdrop", 480)}" alt="" loading="lazy" onerror="this.remove()">` : ""}</span>`;
  const heart = (c, big) => { const on = (S.prefs[K.fav] || []).includes(c.id);
    return `<button class="btn${big ? " big" : " sm"} ovheart${on ? " on" : ""}" data-fav="${c.id}" title="${on ? "Aus den Favoriten entfernen" : "Zu den Favoriten"}">${ico("heart")}${big ? (on ? "Favorit" : "Favorit") : ""}</button>`; };
  const heroHtml = c => {
    const n = c.now, x = c.next;
    return `${pic(c, "ovhpic")}<div class="ovhtx"><div class="ovhch">${badge(c, true)}<div><span class="ovlive"><i></i>LIVE</span><b>${esc(c.name)}</b></div></div>
      ${n ? `<h2>${esc(n.title)}</h2>${n.sub ? `<div class="ovsub">${esc(n.sub)}</div>` : ""}
        <div class="ovtime">${hm(n.start)} – ${hm(n.stop)} · ${ovLeft(n)}</div><div class="ovbar"><i style="width:${ovPct(n)}%"></i></div>
        ${n.descr ? `<p>${esc(n.descr)}</p>` : ""}${x ? `<div class="ovnx"><b>Danach</b> ${hm(x.start)} · ${esc(x.title)}</div>` : ""}` : `<h2>Keine Programmdaten</h2>`}
      <div class="actions"><button class="btn pri big" data-on="${c.id}">${ico("play")}Einschalten</button>
      ${K.prog ? `<a class="btn big" href="${K.prog}">${ico("list")}${K.progLbl}</a>` : `<button class="btn big" data-prog="${c.id}">${ico("list")}Programm</button>`}${heart(c, true)}</div></div>`;
  };
  const rowHtml = c => {
    const n = c.now, x = c.next;
    return `<div class="ovr" tabindex="0" data-on="${c.id}">${pic(c, "ovpic")}<div class="ovch">${badge(c)}<b>${esc(c.name)}</b></div>
      <div class="ovnow">${n ? `<div class="ovt">${esc(n.title)}${n.sub ? ` <span>${esc(n.sub)}</span>` : ""}</div>
        <div class="ovbar sm"><i style="width:${ovPct(n)}%"></i></div><small>${hm(n.start)} – ${hm(n.stop)} · ${ovLeft(n)}</small>` : `<div class="ovt dim">Keine Programmdaten</div>`}</div>
      <div class="ovnx">${n && x ? `<b>Danach</b> ${hm(x.start)} · ${esc(x.title)}` : ""}</div>
      <div class="ovbtn">${heart(c)}${kind === "chan" ? `<button class="btn sm" data-prog="${c.id}" title="Programm">${ico("list")}</button>` : ""}</div></div>`;
  };
  const paint = () => {
    if (v._ov !== tok) return;
    const y = scrollY, fl = favs(), groups = [...new Set(list.map(c => c.group).filter(Boolean))];
    const secs = q ? [[`Suche: „${q}“`, list.filter(hit)]] :
      (fl.length ? [["Favoriten", fl]] : []).concat(groups.length > 1 ? groups.map(g => [g, list.filter(c => c.group === g)]).concat(list.some(c => !c.group) ? [["Weitere Sender", list.filter(c => !c.group)]] : [])
        : [[fl.length ? "Alle Sender" : "", list]]);
    const hero = list.find(c => c.id === heroId);
    v.innerHTML = `<div class="ov"><div class="toolbar"><h1>${K.title}</h1><span class="cnt">${list.length} Sender</span><span style="flex:1"></span>
        <input type="search" class="ovq" placeholder="${K.searchPh}" value="${esc(q)}">${K.prog ? `<a class="btn" href="${K.prog}">${ico("list")}${K.progLbl}</a>` : ""}</div>
      ${!list.length ? `<div class="panel">${K.empty()}</div>` : ""}
      ${hero && !q ? `<section class="ovhero">${heroHtml(hero)}</section>` : ""}
      ${secs.length > 1 ? `<div class="ovchips"><button class="chipb on" data-jump="top">Alle</button>${secs.map((s, i) => `<button class="chipb" data-jump="${i}">${esc(s[0])}</button>`).join("")}</div>` : ""}
      ${secs.map(([g, l], i) => `<section class="ovsec" id="ovs${i}">${g ? `<h2>${esc(g)} <small>${l.length} Sender</small></h2>` : ""}
        ${l.length ? `<div class="ovlist">${l.map(rowHtml).join("")}</div>` : `<p class="dim">Nichts gefunden.</p>`}</section>`).join("")}</div>`;
    scrollTo(0, y);
    const qi = $(".ovq", v);
    qi.oninput = () => { q = qi.value.trim(); const pos = qi.selectionStart; paint(); const n = $(".ovq", v); n.focus(); n.setSelectionRange(pos, pos); };
    const h = $(".ovhero", v);
    if (h) { h.onmouseenter = h.onfocusin = () => hold = true; h.onmouseleave = h.onfocusout = () => hold = false; }
  };
  v.onclick = async e => {
    const f = e.target.closest("[data-fav]");
    if (f) { e.stopPropagation(); await ovFav(K.fav, +f.dataset.fav); return paint(); }
    const p = e.target.closest("[data-prog]");
    if (p) { e.stopPropagation(); return showChannelProgram(+p.dataset.prog, list); }
    const j = e.target.closest("[data-jump]");
    if (j) { const t = j.dataset.jump === "top" ? $(".ov", v) : $("#ovs" + j.dataset.jump, v);
      $$("[data-jump]", v).forEach(b => b.classList.toggle("on", b === j));
      if (t) scrollTo({ top: t.getBoundingClientRect().top + scrollY - 70, behavior: "smooth" }); return; }
    const o = e.target.closest("[data-on]");
    if (o) { const c = list.find(x => x.id === +o.dataset.on); if (c) K.play(c, list); }
  };
  v.onkeydown = e => { if (e.key === "Enter" && e.target.classList.contains("ovr")) e.target.click(); };
  paint();
  // Bühne weiterzappen; nächstes Standbild vorladen
  const rot = setInterval(() => {
    if (v._ov !== tok || !document.body.contains($(".ov", v))) return clearInterval(rot);
    if (hold || q || !$("#player").classList.contains("hidden")) return;
    const l = withNow(); if (l.length < 2) return;
    const i = l.findIndex(c => c.id === heroId), c = l[(i + 1) % l.length], nx = l[(i + 2) % l.length];
    heroId = c.id; const h = $(".ovhero", v); if (h) { h.innerHTML = heroHtml(c); h.classList.remove("in"); void h.offsetWidth; h.classList.add("in"); }
    if (kind === "live") new Image().src = K.snap(nx);
  }, 5000);
  // Programmdaten jede Minute auffrischen
  const ref = setInterval(async () => {
    if (v._ov !== tok || !document.body.contains($(".ov", v))) return clearInterval(ref);
    try { let l = await api(K.list); if (kind === "chan") l = l.filter(c => c.enabled && c.count); list = l; if (!$(".ovq:focus", v)) paint(); } catch (e) { }
  }, 60000);
}
/* Programm eines eigenen Senders (die nächsten 24 Stunden) */
async function showChannelProgram(cid, list) {
  const c = list.find(x => x.id === cid); if (!c) return;
  const items = await api(`/api/channels/${cid}/epg`);
  const box = document.createElement("div"); box.className = "ovmodal";
  box.innerHTML = `<div class="ovmbox"><div class="toolbar"><h2 style="margin:0">${esc(c.name)} – Programm</h2><span style="flex:1"></span><button class="btn" data-x>${ico("close")}</button></div>
    <div class="ovplist">${items.slice(0, 60).map((p, i) => `<div class="ovpi${i === 0 ? " on" : ""}"><b>${hm(p.start)}</b><div><div class="ovt">${esc(p.title)}</div>${p.descr ? `<small>${esc(p.descr)}</small>` : ""}</div></div>`).join("")}</div></div>`;
  box.onclick = e => { if (e.target === box || e.target.closest("[data-x]")) box.remove(); };
  document.body.appendChild(box);
}

/* ---------- Schnellzugriff auf Favoriten (Kopfzeile) ---------- */
function quickFavInit() {
  if ($("#qfav")) return;
  const wrap = document.createElement("div"); wrap.id = "qfav";
  wrap.innerHTML = `<button data-q="live" title="TV-Favoriten">${ico("live")}</button><button data-q="chan" title="Sender-Favoriten">${ico("chan")}</button>
    <button data-q="saver" title="Bildschirmschoner starten">${ico("moon")}</button><div id="qfdrop" class="hidden"></div>`;
  $("#search").after(wrap);
  wrap.onclick = async e => {
    e.stopPropagation();
    const b = e.target.closest("[data-q]"), d = $("#qfdrop");
    if (!b) return;
    if (b.dataset.q === "saver") { d.classList.add("hidden"); return saverStart(); }
    if (!d.classList.contains("hidden") && d.dataset.k === b.dataset.q) { d.classList.add("hidden"); return; }
    const K = OVK[b.dataset.q]; d.dataset.k = b.dataset.q; d.classList.remove("hidden");
    d.innerHTML = `<div class="qfh">${K.title}-Favoriten</div><div class="dim" style="padding:8px 12px">Lädt …</div>`;
    let list = []; try { list = await api(K.list); } catch (x) { }
    const fl = (S.prefs[K.fav] || []).map(id => list.find(c => c.id === id)).filter(Boolean).slice(0, 3);
    d.innerHTML = `<div class="qfh">${K.title}-Favoriten</div>${fl.map(c => `<button class="qfi" data-c="${c.id}">
      ${b.dataset.q === "live" ? `<span class="qfp"><img src="${K.snap(c)}" alt="" onerror="this.remove()"></span>` : `<span class="qfp">${c.now && c.now.id ? `<img src="${img(c.now.id, "backdrop", 300)}" alt="" onerror="this.remove()">` : ""}</span>`}
      <span class="qft"><b>${esc(c.name)}</b><small>${c.now ? esc(c.now.title) : "Live"}</small></span>${ico("play")}</button>`).join("") ||
      `<p class="dim" style="padding:4px 12px">Noch keine Favoriten – in der Übersicht beim Sender auf das Herz klicken.</p>`}
      <a class="qfm" href="#/${b.dataset.q === "live" ? "live" : "channels"}">Alle Sender ›</a>`;
    $$(".qfi", d).forEach(x => x.onclick = ev => { ev.stopPropagation(); d.classList.add("hidden"); const c = list.find(y => y.id === +x.dataset.c); K.play(c, list); });
  };
  document.addEventListener("click", () => $("#qfdrop")?.classList.add("hidden"));
}

/* ---------- Bildschirmschoner ----------
   Nach der eingestellten Zeit ohne Eingabe (nicht während der Wiedergabe): Hintergrundbilder deiner Filme und Serien
   mit Titel, dazu die Uhr. Jede Taste, Mausbewegung oder Berührung beendet ihn. */
const SV = { last: Date.now(), el: null, t: null, items: [], i: 0 };
["mousemove", "keydown", "pointerdown", "wheel", "touchstart"].forEach(ev => document.addEventListener(ev, () => {
  SV.last = Date.now(); if (SV.el && Date.now() - SV.started > 800) saverStop();
}, { capture: true, passive: true }));
setInterval(() => {
  if (SV.el || !S.user || S.prefs.saver_on === false) return;
  if (!$("#player").classList.contains("hidden") && P.v && !P.v.paused) { SV.last = Date.now(); return; }
  if (!$("#player").classList.contains("hidden") && P.live) { SV.last = Date.now(); return; }
  if (Date.now() - SV.last > (S.prefs.saver_min || 10) * 60000) saverStart();
}, 5000);
async function saverStart() {
  if (SV.el) return;
  try { SV.items = await api("/api/saver"); } catch (e) { SV.items = []; }
  const el = document.createElement("div"); el.id = "saver";
  el.innerHTML = `<div class="svimg a"></div><div class="svimg b"></div><div class="svshade"></div>
    ${S.prefs.saver_clock !== false ? `<div class="svclock"><b></b><span></span></div>` : ""}<div class="svinfo"></div>`;
  document.body.appendChild(el); SV.el = el; SV.started = Date.now(); SV.i = 0; SV.flip = false;
  const clock = () => { const c = $(".svclock", el); if (!c) return; const d = new Date();
    $("b", c).textContent = d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
    $("span", c).textContent = d.toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "long" }); };
  const show = () => {
    if (!SV.items.length) return;
    const it = SV.items[SV.i++ % SV.items.length], nx = SV.items[SV.i % SV.items.length];
    SV.flip = !SV.flip;
    const on = $(SV.flip ? ".svimg.a" : ".svimg.b", el), off = $(SV.flip ? ".svimg.b" : ".svimg.a", el);
    on.style.backgroundImage = `url('${img(it.id, "backdrop", 1920)}')`; on.classList.add("on"); off.classList.remove("on");
    $(".svinfo", el).innerHTML = `${it.has_logo ? `<img src="${img(it.id, "logo", 600)}" alt="${esc(it.title)}" onerror="this.outerHTML='<h2>'+this.alt+'</h2>'">` : `<h2>${esc(it.title)}</h2>`}
      <div class="dim">${[it.year, it.kind === "show" ? "Serie" : "Film"].filter(Boolean).join(" · ")}</div>`;
    new Image().src = img(nx.id, "backdrop", 1920);
  };
  clock(); show();
  SV.t = setInterval(clock, 1000);
  SV.show = setInterval(show, 20000);
}
function saverStop() {
  if (!SV.el) return;
  clearInterval(SV.t); clearInterval(SV.show); SV.el.remove(); SV.el = null; SV.last = Date.now();
}

/* ---------- Einbinden ---------- */
(() => {
  const set = (route, view) => { const x = S.ext.find(e => e.route === route); if (x) x.view = view; };
  set("live", (v, rest, seq) => viewOverview(v, "live", seq));
  set("channels", (v, rest, seq) => viewOverview(v, "chan", seq));
  if (!$("#i-moon")) $("svg symbol:last-of-type").insertAdjacentHTML("afterend",
    `<symbol id="i-moon" viewBox="0 0 24 24"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></symbol>`);
  quickFavInit();
})();
