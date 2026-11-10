/* Lichtspiel – Radio: selbst eingetragene Sender, Player-Leiste unten (läuft beim Blättern weiter), Favoriten je Profil. */
"use strict";
const R = { list: [], cur: null, audio: null, nowT: null, title: "" };

function radioLogo(c, cls = "rlogo") {
  return `<span class="${cls}">${c.has_logo ? `<img src="/api/radio/${c.id}/logo" alt="" onerror="this.parentNode.textContent=${esc(JSON.stringify(ovShort(c.name)))}">` : esc(ovShort(c.name))}</span>`;
}
async function radioLoad() { try { R.list = await api("/api/radio"); } catch (e) { R.list = []; } return R.list; }

/* ---------- Abspielen ---------- */
function radioPlay(c) {
  if (!c) return;
  if (!$("#player").classList.contains("hidden")) closePlayer(true);          // Film/Live-TV beenden
  if (!R.audio) { R.audio = new Audio(); R.audio.preload = "none";
    R.audio.addEventListener("playing", () => radioBar());
    R.audio.addEventListener("pause", () => radioBar());
    R.audio.addEventListener("error", () => { if (R.cur) toast("Sender nicht erreichbar: " + R.cur.name); radioBar(); }); }
  R.cur = c; R.title = "";
  R.audio.src = `/api/radio/${c.id}/stream?_=${Date.now()}`;
  R.audio.play().catch(() => { });
  S.prefs.radio_last = c.id; api("/api/me/prefs", { method: "PUT", body: { radio_last: c.id } }).catch(() => { });
  radioBar(); radioNow();
  clearInterval(R.nowT); R.nowT = setInterval(radioNow, 20000);
}
function radioToggle() { if (!R.audio || !R.cur) return; if (R.audio.paused) { R.audio.src = `/api/radio/${R.cur.id}/stream?_=${Date.now()}`; R.audio.play().catch(() => { }); } else R.audio.pause(); }
function radioStop() { if (R.audio) { R.audio.pause(); R.audio.removeAttribute("src"); R.audio.load(); } R.cur = null; clearInterval(R.nowT); radioBar(); }
async function radioNow() {
  if (!R.cur) return;
  try { const j = await api(`/api/radio/${R.cur.id}/now`); R.title = j.title || ""; } catch (e) { R.title = ""; }
  radioBar();
}
function radioBar() {
  let b = $("#rbar");
  if (!R.cur) { b?.remove(); document.body.classList.remove("rbar"); return; }
  if (!b) { b = document.createElement("div"); b.id = "rbar"; document.body.appendChild(b); }
  document.body.classList.add("rbar");
  const on = R.audio && !R.audio.paused, fav = (S.prefs.radio_favs || []).includes(R.cur.id);
  b.innerHTML = `${radioLogo(R.cur)}<div class="rbt"><small>RADIO${on ? ` <i class="eq"><b></b><b></b><b></b></i>` : " · pausiert"}</small><b>${esc(R.cur.name)}</b>${R.title ? `<span>${esc(R.title)}</span>` : ""}</div>
    <button class="rbb" data-r="fav" title="Favorit">${ico("heart")}</button><button class="rbb big" data-r="play" title="Pause/Weiter">${ico(on ? "pause" : "play")}</button>
    <button class="rbb" data-r="stop" title="Radio aus">${ico("close")}</button>`;
  $("[data-r=fav]", b).classList.toggle("on", fav);
  b.onclick = async e => { const x = e.target.closest("[data-r]"); if (!x) return;
    if (x.dataset.r === "play") radioToggle(); else if (x.dataset.r === "stop") radioStop();
    else { await ovFav("radio_favs", R.cur.id); radioBar(); if (location.hash.startsWith("#/radio")) route(); } };
}

/* ---------- Radio-Seite ---------- */
async function viewRadio(v, rest, seq) {
  const list = await radioLoad();
  if (seq !== routeSeq) return;
  let q = "";
  const paint = () => {
    const favs = (S.prefs.radio_favs || []).map(id => list.find(c => c.id === id)).filter(Boolean);
    const hit = c => !q || [c.name, c.group].some(x => ovNorm(x).includes(ovNorm(q)));
    const groups = [...new Set(list.map(c => c.group).filter(Boolean))];
    const secs = q ? [[`Suche: „${q}“`, list.filter(hit)]] : (favs.length ? [["Favoriten", favs]] : []).concat(
      groups.length > 1 ? groups.map(g => [g, list.filter(c => c.group === g)]).concat(list.some(c => !c.group) ? [["Weitere Sender", list.filter(c => !c.group)]] : []) : [[favs.length ? "Alle Sender" : "", list]]);
    const tile = c => { const fav = (S.prefs.radio_favs || []).includes(c.id), on = R.cur && R.cur.id === c.id;
      return `<div class="rtile${on ? " on" : ""}" tabindex="0" data-rc="${c.id}">${radioLogo(c, "rtl")}<b>${esc(c.name)}</b>
        <button class="rfav${fav ? " on" : ""}" data-rf="${c.id}" title="Favorit">${ico("heart")}</button></div>`; };
    v.innerHTML = `<div class="toolbar"><h1>Radio</h1><span class="cnt">${list.length} Sender</span><span style="flex:1"></span>
      <input type="search" class="rq" placeholder="Sender suchen" value="${esc(q)}">${S.user.admin ? `<a class="btn" href="#/settings/radio">Sender verwalten</a>` : ""}</div>
      ${!list.length ? `<div class="panel">Noch keine Radiosender. ${S.user.admin ? `Unter <a href="#/settings/radio" style="color:var(--acc)">Einstellungen → Radio</a> eintragen (von Hand oder als M3U/PLS-Liste).` : ""}</div>` : ""}
      ${secs.map(([g, l]) => `<section class="hub">${g ? `<h2>${esc(g)}</h2>` : ""}${l.length ? `<div class="rgrid">${l.map(tile).join("")}</div>` : `<p class="dim">Nichts gefunden.</p>`}</section>`).join("")}`;
    const qi = $(".rq", v); qi.oninput = () => { q = qi.value.trim(); const p = qi.selectionStart; paint(); const n = $(".rq", v); n.focus(); n.setSelectionRange(p, p); };
  };
  v.onclick = async e => {
    const f = e.target.closest("[data-rf]"); if (f) { e.stopPropagation(); await ovFav("radio_favs", +f.dataset.rf); paint(); radioBar(); return; }
    const t = e.target.closest("[data-rc]"); if (t) { const c = list.find(x => x.id === +t.dataset.rc); if (R.cur && R.cur.id === c.id) radioToggle(); else radioPlay(c); setTimeout(paint, 300); }
  };
  v.onkeydown = e => { if (e.key === "Enter" && e.target.classList.contains("rtile")) e.target.click(); };
  paint();
}

/* ---------- Einstellungen: Radio (Admin) ---------- */
async function setRadio(b) {
  const [j, users] = await Promise.all([api("/api/radio/admin"), api("/api/users")]);
  b.innerHTML = `<h2>Radio</h2><p style="color:var(--dim)">Radiosender trägst du selbst ein – einzeln oder als Liste (M3U/M3U8/PLS). Lichtspiel fragt kein Online-Verzeichnis ab.</p>
    <div class="panel"><h3>Sender (${j.stations.length})</h3><table class="tbl"><tr><th>Logo</th><th>Name</th><th>Gruppe</th><th>Adresse</th><th></th></tr>
    ${j.stations.map(s => `<tr><td>${radioLogo(s)}</td><td><input type="text" data-e="name" data-id="${s.id}" value="${esc(s.name)}"></td>
      <td><input type="text" data-e="group" data-id="${s.id}" value="${esc(s.group)}" style="width:120px"></td>
      <td style="word-break:break-all;font-size:12.5px;color:var(--dim)">${esc(s.url)}</td>
      <td style="white-space:nowrap"><button class="btn sm" data-t="${s.id}">${ico("play")}</button> <button class="btn sm ${s.enabled ? "on" : ""}" data-en="${s.id}" data-v="${s.enabled ? 0 : 1}">${s.enabled ? "An" : "Aus"}</button>
      <button class="btn sm danger" data-del="${s.id}">×</button></td></tr>`).join("") || `<tr><td colspan="5" class="dim">Noch keine Sender</td></tr>`}</table></div>
    <div class="panel"><h3>Sender hinzufügen</h3><div class="fr"><label>Name</label><input type="text" id="raN" style="flex:1"></div>
      <div class="fr"><label>Stream-Adresse</label><input type="url" id="raU" style="flex:1" placeholder="https://…/stream.mp3 oder …m3u8"></div>
      <div class="fr"><label>Logo-Adresse (optional)</label><input type="url" id="raL" style="flex:1"></div>
      <div class="fr"><label>Gruppe (optional)</label><input type="text" id="raG"></div>
      <div class="actions"><button class="btn pri" id="raAdd">Hinzufügen</button></div></div>
    <div class="panel"><h3>Liste übernehmen</h3><div class="fr"><label>Adresse der Liste</label><input type="url" id="riU" style="flex:1" placeholder="https://…/radio.m3u"></div>
      <div class="actions"><button class="btn" id="riGo">Liste laden</button><label class="btn">Datei wählen…<input type="file" hidden id="riF" accept=".m3u,.m3u8,.pls,.txt"></label></div>
      <p class="dim" style="margin:0">Schon vorhandene Adressen werden übersprungen. Logos und Gruppen aus #EXTINF (tvg-logo, group-title) werden übernommen.</p></div>
    <div class="panel"><h3>Wer darf Radio hören?</h3>${accessHtml(j.access, users)}</div>`;
  const re = () => setRadio(b);
  $("#raAdd").onclick = async () => { try { await api("/api/radio", { body: { name: $("#raN").value, url: $("#raU").value, logo: $("#raL").value, group: $("#raG").value } }); toast("Hinzugefügt"); re(); } catch (e) { toast(e.message); } };
  const imp = async body => { try { const r = await api("/api/radio/import", { body }); toast(`${r.added} von ${r.found} Sendern übernommen`); re(); } catch (e) { toast(e.message); } };
  $("#riGo").onclick = () => imp({ url: $("#riU").value.trim() });
  $("#riF").onchange = async e => { const f = e.target.files[0]; if (f) imp({ text: await f.text() }); };
  $$("[data-e]", b).forEach(i => i.onchange = () => api(`/api/radio/${i.dataset.id}`, { method: "PUT", body: { [i.dataset.e]: i.value.trim() } }).then(() => toast("Gespeichert", 900)));
  $$("[data-en]", b).forEach(x => x.onclick = async () => { await api(`/api/radio/${x.dataset.en}`, { method: "PUT", body: { enabled: +x.dataset.v } }); re(); });
  $$("[data-del]", b).forEach(x => x.onclick = async () => { if (!confirm("Sender entfernen?")) return; await api(`/api/radio/${x.dataset.del}`, { method: "DELETE" }); re(); });
  $$("[data-t]", b).forEach(x => x.onclick = () => { const s = j.stations.find(y => y.id === +x.dataset.t); radioPlay(s); });
  bindAccess(b, "/api/radio/access");
}

/* ---------- Einbinden ---------- */
S.ext.push({ route: "radio", nav: "Radio", icon: "radio", view: viewRadio, settings: "Radio", settingsId: "radio", settingsView: setRadio, settingsAdmin: true });
(() => {
  if (!$("#i-radio")) $("svg symbol:last-of-type").insertAdjacentHTML("afterend",
    `<symbol id="i-radio" viewBox="0 0 24 24"><rect x="3" y="8" width="18" height="12" rx="2"/><path d="M7 8l10-5"/><circle cx="15.5" cy="14" r="2.5"/><path d="M6.5 12.5h4M6.5 15.5h4"/></symbol>`);
  // Schnellzugriff: Radio-Favoriten
  const qf = $("#qfav");
  if (qf && !$("[data-q=radio]", qf)) {
    $("[data-q=saver]", qf).insertAdjacentHTML("beforebegin", `<button data-q="radio" title="Radio-Favoriten">${ico("radio")}</button>`);
    qf.addEventListener("click", async e => {
      const b = e.target.closest("[data-q=radio]"); if (!b) return;
      e.stopImmediatePropagation();
      const d = $("#qfdrop");
      if (!d.classList.contains("hidden") && d.dataset.k === "radio") { d.classList.add("hidden"); return; }
      d.dataset.k = "radio"; d.classList.remove("hidden");
      const list = await radioLoad(), fl = (S.prefs.radio_favs || []).map(id => list.find(c => c.id === id)).filter(Boolean).slice(0, 3);
      d.innerHTML = `<div class="qfh">Radio-Favoriten</div>${fl.map(c => `<button class="qfi" data-c="${c.id}">${radioLogo(c, "qfp rl")}<span class="qft"><b>${esc(c.name)}</b><small>${esc(c.group || "Radio")}</small></span>${ico("play")}</button>`).join("") ||
        `<p class="dim" style="padding:4px 12px">Noch keine Favoriten – auf der Radio-Seite beim Sender auf das Herz klicken.</p>`}<a class="qfm" href="#/radio">Radio öffnen ›</a>`;
      $$(".qfi", d).forEach(x => x.onclick = ev => { ev.stopPropagation(); d.classList.add("hidden"); radioPlay(list.find(y => y.id === +x.dataset.c)); location.hash = "#/radio"; });
    }, true);
  }
  // Film oder Live-TV starten → Radio anhalten
  const op = window.openPlayer; window.openPlayer = function (...a) { if (R.audio && !R.audio.paused) R.audio.pause(); return op.apply(this, a); };
  const ol = window.openLive; window.openLive = function (...a) { if (R.audio && !R.audio.paused) R.audio.pause(); return ol.apply(this, a); };
})();
