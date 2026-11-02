/* Lichtspiel – Live-TV (eigene Senderlisten) und eigene TV-Sender. */
"use strict";
const hm = t => new Date(t * 1000).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
const pct = (p, now = Date.now() / 1000) => p ? Math.max(0, Math.min(100, (now - p.start) / (p.stop - p.start) * 100)) : 0;

/* ---------- Live-TV ---------- */
function chanTile(c, logoUrl, onclick) {
  const n = c.now;
  return `<div class="card wide" tabindex="0" data-c="${c.id}" style="cursor:pointer"><div class="pic" style="background:#1a2230;display:flex;align-items:center;justify-content:center">
    ${c.has_logo ? `<img src="${logoUrl}" alt="" style="object-fit:contain;padding:18% 22%" onerror="this.remove()">` : ""}
    <div class="ph" style="z-index:-1">${esc(c.name)}</div>${c.number ? `<span class="badge" style="left:6px;right:auto">${c.number}</span>` : ""}
    ${n ? `<div class="bar"><i style="width:${pct(n)}%"></i></div>` : ""}</div>
    <div class="t">${esc(c.name)}</div><div class="s">${n ? `${hm(n.start)} ${esc(n.title)}` : "Kein Programm"}</div>
    ${c.next ? `<div class="s" style="opacity:.7">${hm(c.next.start)} ${esc(c.next.title)}</div>` : ""}</div>`;
}
async function viewLive(v, rest, seq) {
  const ch = await api("/api/live");
  if (seq !== routeSeq) return;
  v.innerHTML = `<div class="toolbar"><h1>Live-TV</h1><span class="cnt">${ch.length} Sender</span><span style="flex:1"></span>
    <a class="btn" href="#/guide">${ico("list")}Programmführer</a></div>` +
    (ch.length ? `<div class="grid" style="--card:260px">${ch.map(c => chanTile(c, `/api/live/${c.id}/logo`)).join("")}</div>` :
      `<div class="panel">Keine Sender. ${S.user.admin ? `Senderlisten (M3U/M3U8) unter <a style="color:var(--acc)" href="#/settings/live">Einstellungen → Live-TV</a> eintragen.` : ""}</div>`);
  $$("[data-c]", v).forEach(e => e.onclick = () => openLive(+e.dataset.c, ch));
}
async function viewGuide(v, rest, seq) {
  const now = Date.now() / 1000, frm = Math.floor(now / 1800) * 1800, hours = 6, to = frm + hours * 3600;
  const [ch, epg] = await Promise.all([api("/api/live"), api(`/api/live/epg?from=${frm}&to=${to}`)]);
  if (seq !== routeSeq) return;
  const W = 5; // Pixel pro Minute
  const x = t => (Math.max(t, frm) - frm) / 60 * W;
  let h = `<div class="toolbar"><h1>Programmführer</h1><span style="flex:1"></span><a class="btn" href="#/live">Senderübersicht</a></div>
    <div class="guide"><div class="gh"><div class="gc"></div><div class="gt" style="width:${hours * 60 * W}px">${Array.from({ length: hours * 2 }, (_, i) =>
    `<span style="left:${i * 30 * W}px">${hm(frm + i * 1800)}</span>`).join("")}<i class="gnow" style="left:${x(now)}px"></i></div></div>`;
  for (const c of ch) {
    const ps = epg[c.id] || [];
    h += `<div class="gr"><div class="gc" data-c="${c.id}">${c.has_logo ? `<img src="/api/live/${c.id}/logo" alt="" onerror="this.remove()">` : ""}<span>${esc(c.name)}</span></div>
      <div class="gt" style="width:${hours * 60 * W}px">${ps.map(p => `<div class="gp${p.start <= now && p.stop > now ? " on" : ""}" data-c="${c.id}" title="${esc(p.title)}${p.descr ? "\n\n" + esc(p.descr) : ""}"
      style="left:${x(p.start)}px;width:${Math.max(4, x(p.stop) - x(p.start) - 3)}px"><b>${esc(p.title)}</b><span>${hm(p.start)}–${hm(p.stop)}${p.sub ? " · " + esc(p.sub) : ""}</span></div>`).join("")}</div></div>`;
  }
  v.innerHTML = h + "</div>";
  $$("[data-c]", v).forEach(e => e.onclick = () => openLive(+e.dataset.c, ch));
}
function openLive(cid, list) {
  closePlayer(true);
  const c = list.find(x => x.id === cid); if (!c) return;
  const el = $("#player"); el.classList.remove("hidden"); el.classList.add("ui");
  el.innerHTML = `<video playsinline autoplay></video><div class="center"><div class="spin"></div></div>
    <div class="ov"><div class="ptop"><div class="tt"><h2>${c.number ? c.number + " · " : ""}${esc(c.name)}</h2>
    <div class="st">${c.now ? `${hm(c.now.start)}–${hm(c.now.stop)} ${esc(c.now.title)}` : ""}</div>
    <div class="info">${c.now && c.now.descr ? esc(c.now.descr.slice(0, 300)) : ""}</div></div>
    <button id="lClose" style="background:none;border:0;color:#fff">${ico("close")}</button></div>
    <div class="pbot"><div class="ctl"><button id="lPrev" title="Sender zurück (Bild ↑)">${ico("back")}</button><button id="lNext" title="Sender vor (Bild ↓)">${ico("fwd")}</button>
    <span class="tm">${c.next ? `Danach ${hm(c.next.start)}: ${esc(c.next.title)}` : ""}</span><span class="sp"></span>
    <button id="lFull">${ico("full")}</button></div></div></div>`;
  const v = $("video", el); let mode = "copy";
  P.v = v; P.info = null; P.live = { cid, list };
  const start = () => { v.src = `/api/live/${cid}/stream?mode=${mode}&_=${Date.now()}`; v.play().catch(() => { }); };
  v.addEventListener("playing", () => $(".center", el).classList.add("hidden"));
  v.addEventListener("waiting", () => $(".center", el).classList.remove("hidden"));
  v.addEventListener("error", () => { if (mode === "copy") { mode = "transcode"; toast("Sender wird umgewandelt …"); start(); } else playerError("Sender nicht erreichbar."); });
  el.onmousemove = showUi;
  const zap = d => { const i = list.findIndex(x => x.id === cid); openLive(list[(i + d + list.length) % list.length].id, list); };
  $("#lClose").onclick = () => { P.live = null; closePlayer(); };
  $("#lPrev").onclick = () => zap(-1); $("#lNext").onclick = () => zap(1);
  $("#lFull").onclick = toggleFull;
  P.liveKeys = e => { if (e.key === "PageUp") zap(-1); else if (e.key === "PageDown") zap(1); else if (e.key === "Escape" && !document.fullscreenElement) { P.live = null; closePlayer(); } };
  start(); showUi();
}
document.addEventListener("keydown", e => { if (P.live && P.liveKeys && !$("#player").classList.contains("hidden")) P.liveKeys(e); });

/* ---------- Eigene Sender ---------- */
async function viewChannels(v, rest, seq) {
  const ch = await api("/api/channels");
  if (seq !== routeSeq) return;
  const list = ch.filter(c => c.enabled && c.count);
  v.innerHTML = `<div class="toolbar"><h1>Sender</h1><span class="cnt">${list.length} eigene Sender</span><span style="flex:1"></span>
    ${S.user.admin ? `<a class="btn" href="#/settings/sender">Sender verwalten</a>` : ""}</div>` +
    (list.length ? `<div class="grid" style="--card:260px">${list.map(c => chanTile(c, `/api/channels/${c.id}/logo`)).join("")}</div>` :
      `<div class="panel">Noch keine eigenen Sender. ${S.user.admin ? `Unter <a style="color:var(--acc)" href="#/settings/sender">Einstellungen → Eigene Sender</a> anlegen.` : ""}</div>`);
  $$("[data-c]", v).forEach(e => e.onclick = () => openChannel(+e.dataset.c));
}
window.openChannel = async function (cid) {
  try {
    const t = await api(`/api/channels/${cid}/tune`);
    await openPlayer(t.item, { start: t.offset, tv: { id: cid, name: t.channel.name } });
  } catch (e) { toast(e.message); }
};

/* ---------- Einstellungen: Live-TV ---------- */
async function setLive(b) {
  const [j, users] = await Promise.all([api("/api/live/sources"), api("/api/users")]);
  b.innerHTML = `<h2>Live-TV</h2><p style="color:var(--dim)">Senderlisten im M3U/M3U8-Format und Programmdaten im XMLTV-Format – per Adresse oder als Datei. Es werden nur Quellen benutzt, die du hier einträgst.</p>
    ${j.sources.map(s => `<div class="panel"><h3>${esc(s.name)} <span style="color:var(--dim);font-weight:400;font-size:13px">${esc(s.msg || "")}${s.updated ? " · " + fmtDate(s.updated) : ""}</span></h3>
      <div class="fr"><label>Senderliste</label><input type="text" style="flex:1" data-f="m3u_url" data-s="${s.id}" value="${esc(s.m3u_url)}"><label class="btn sm">Datei…<input type="file" hidden data-up="m3u" data-s="${s.id}"></label></div>
      <div class="fr"><label>Programm (XMLTV)</label><input type="text" style="flex:1" data-f="xmltv_url" data-s="${s.id}" value="${esc(s.xmltv_url || "")}"><label class="btn sm">Datei…<input type="file" hidden data-up="xmltv" data-s="${s.id}"></label></div>
      <div class="actions"><button class="btn sm" data-rf="${s.id}">Neu laden</button><button class="btn sm" data-en="${s.id}" data-v="${s.enabled ? 0 : 1}">${s.enabled ? "Abschalten" : "Einschalten"}</button>
      <button class="btn sm danger" data-del="${s.id}">Entfernen</button><button class="btn sm" data-tg="${s.id}">Sender (${s.channels.length}) ein-/ausblenden</button></div>
      <div class="hidden" id="chs${s.id}"><table class="tbl"><tr><th>Nr.</th><th>Sender</th><th>Gruppe</th><th>Programm</th><th></th></tr>${s.channels.map(c => `<tr>
      <td><input type="number" style="width:70px" data-num="${c.id}" value="${c.number ?? ""}"></td><td>${esc(c.name)}</td><td>${esc(c.grp || "")}</td><td>${c.epg ? c.epg + " Einträge" : "–"}</td>
      <td><button class="btn sm ${c.enabled ? "on" : ""}" data-ce="${c.id}" data-v="${c.enabled ? 0 : 1}">${c.enabled ? "An" : "Aus"}</button></td></tr>`).join("")}</table></div></div>`).join("")}
    <div class="panel"><h3>Neue Senderliste</h3><div class="fr"><label>Name</label><input type="text" id="nsN" value="Senderliste"></div>
    <div class="fr"><label>M3U/M3U8-Adresse</label><input type="url" id="nsM" style="flex:1" placeholder="https://…/liste.m3u8"></div>
    <div class="fr"><label>XMLTV-Adresse (optional)</label><input type="url" id="nsX" style="flex:1" placeholder="https://…/epg.xml.gz"></div>
    <div class="actions"><button class="btn pri" id="nsAdd">Hinzufügen</button></div></div>
    <div class="panel"><h3>Wer darf Live-TV sehen?</h3>${accessHtml(j.access, users)}</div>`;
  const reload = () => setLive(b);
  $$("[data-f]", b).forEach(i => i.onchange = async () => { await api(`/api/live/sources/${i.dataset.s}`, { method: "PUT", body: { [i.dataset.f]: i.value.trim() } }); toast("Gespeichert – wird neu geladen"); });
  $$("[data-up]", b).forEach(i => i.onchange = async () => {
    const f = i.files[0]; if (!f) return; toast("Lädt hoch …", 10000);
    const r = await fetch(`/api/live/sources/${i.dataset.s}/upload/${i.dataset.up}`, { method: "POST", body: f });
    toast(r.ok ? "Hochgeladen" : "Fehler beim Hochladen"); reload();
  });
  $$("[data-rf]", b).forEach(x => x.onclick = async () => { toast("Lädt …", 20000); await api(`/api/live/sources/${x.dataset.rf}/refresh`, { body: {} }); toast("Fertig"); reload(); });
  $$("[data-en]", b).forEach(x => x.onclick = async () => { await api(`/api/live/sources/${x.dataset.en}`, { method: "PUT", body: { enabled: +x.dataset.v } }); reload(); });
  $$("[data-del]", b).forEach(x => x.onclick = async () => { if (!confirm("Senderliste entfernen?")) return; await api(`/api/live/sources/${x.dataset.del}`, { method: "DELETE" }); reload(); });
  $$("[data-tg]", b).forEach(x => x.onclick = () => $("#chs" + x.dataset.tg).classList.toggle("hidden"));
  $$("[data-ce]", b).forEach(x => x.onclick = async () => { await api(`/api/live/channels/${x.dataset.ce}`, { method: "PUT", body: { enabled: +x.dataset.v } });
    x.dataset.v = x.dataset.v === "1" ? "0" : "1"; const on = x.dataset.v === "0"; x.classList.toggle("on", on); x.textContent = on ? "An" : "Aus"; });
  $$("[data-num]", b).forEach(i => i.onchange = () => api(`/api/live/channels/${i.dataset.num}`, { method: "PUT", body: { number: i.value ? +i.value : null } }));
  $("#nsAdd").onclick = async () => {
    try { await api("/api/live/sources", { body: { name: $("#nsN").value, m3u_url: $("#nsM").value, xmltv_url: $("#nsX").value } }); toast("Hinzugefügt – Sender werden geladen"); setTimeout(reload, 2500); }
    catch (e) { toast(e.message); }
  };
  bindAccess(b, "/api/live/access");
}
function accessHtml(acc, users) {
  const all = acc === null || acc === undefined;
  return `${seg("acc_all", [[true, "Alle Benutzer"], [false, "Nur ausgewählte"]], all)}
    <div id="accList" class="${all ? "hidden" : ""}" style="margin-top:10px">${users.filter(u => !u.admin).map(u => `<label style="display:block"><input type="checkbox" value="${u.id}" ${(acc || []).includes(u.id) ? "checked" : ""}> ${esc(u.name)}</label>`).join("") || "<span style='color:var(--dim)'>Keine weiteren Benutzer</span>"}
    <div style="color:var(--dim);font-size:13px;margin-top:6px">Administratoren haben immer Zugriff.</div></div>`;
}
function bindAccess(b, url) {
  const save = () => api(url, { method: "PUT", body: { users: $("#accList").classList.contains("hidden") ? null : $$("#accList input:checked").map(x => +x.value) } }).then(() => toast("Gespeichert", 1000));
  $$('[data-seg="acc_all"] button', b).forEach(x => x.addEventListener("click", () => { $("#accList").classList.toggle("hidden", JSON.parse(x.dataset.v)); setTimeout(save); }));
  $$('[data-seg="acc_all"] button', b).forEach(x => x.addEventListener("click", () => $$('[data-seg="acc_all"] button', b).forEach(y => y.classList.toggle("on", y === x))));
  $$("#accList input", b).forEach(i => i.onchange = save);
}

/* ---------- Einstellungen: eigene Sender ---------- */
async function setSender(b, open) {
  const [ch, users, libs] = await Promise.all([api("/api/channels"), api("/api/users"), api("/api/libraries")]);
  const acc = (await api("/api/settings").catch(() => ({}))).channels_access;
  b.innerHTML = `<h2>Eigene Sender</h2><p style="color:var(--dim)">Filme und Folgen aus deinen Bibliotheken laufen hier als durchgehendes Programm – wie ein Fernsehsender.</p>
    <div class="panel"><table class="tbl"><tr><th>Nr.</th><th>Logo</th><th>Name</th><th>Titel</th><th>Läuft gerade</th><th></th></tr>
    ${ch.map(c => `<tr><td>${c.number ?? ""}</td><td>${c.has_logo ? `<img src="/api/channels/${c.id}/logo?${Date.now()}" style="height:30px">` : ""}</td><td><b>${esc(c.name)}</b>${c.enabled ? "" : " <span style='color:var(--dim)'>(aus)</span>"}</td>
    <td>${c.count}</td><td>${c.now ? esc(c.now.title) : "–"}</td><td><button class="btn sm" data-ed="${c.id}">Bearbeiten</button></td></tr>`).join("") || `<tr><td colspan="6" style="color:var(--dim)">Noch keine Sender</td></tr>`}</table>
    <div class="actions"><input type="text" id="ncN" placeholder="Name des neuen Senders"><button class="btn pri" id="ncAdd">+ Sender</button></div></div>
    <div id="chEdit"></div><div class="panel"><h3>Wer darf die Sender sehen?</h3>${accessHtml(acc, users)}</div>`;
  $("#ncAdd").onclick = async () => { try { const r = await api("/api/channels", { body: { name: $("#ncN").value } }); setSender(b, r.id); } catch (e) { toast(e.message); } };
  $$("[data-ed]", b).forEach(x => x.onclick = () => editChannel(b, ch.find(c => c.id === +x.dataset.ed), libs));
  bindAccess(b, "/api/channels/access");
  if (open) { const c = (await api("/api/channels")).find(c => c.id === open); if (c) editChannel(b, c, libs); }
}
async function editChannel(b, c, libs) {
  const box = $("#chEdit");
  const items = await api(`/api/channels/${c.id}/items`);
  const total = items.reduce((a, r) => a + r.len, 0);
  box.innerHTML = `<div class="panel"><h3>Sender bearbeiten: ${esc(c.name)}</h3>
    <div class="fr"><label>Name</label><input type="text" id="ceN" value="${esc(c.name)}"></div>
    <div class="fr"><label>Nummer</label><input type="number" id="ceNum" value="${c.number ?? ""}" style="width:90px"></div>
    <div class="fr"><label>Logo</label><label class="btn sm">Bild wählen…<input type="file" hidden id="ceLogo" accept="image/png,image/jpeg,image/webp"></label></div>
    <div class="fr"><span class="l">Sichtbar</span>${seg("enabled", [[true, "Ja"], [false, "Nein"]], c.enabled)}</div>
    <div class="fr"><span class="l">Hinzufügen</span><div style="flex:1"><input type="text" id="ceQ" placeholder="Film oder Serie suchen …" style="width:100%">
    <div id="ceRes" class="dirpick hidden"></div><div class="actions">${libs.map(l => `<button class="btn sm" data-lib="${l.id}">Alle aus „${esc(l.name)}“</button>`).join("")}</div></div></div>
    <h3 style="margin-top:16px">Programm: ${items.length} Titel · ${fmtDur(total)}</h3>
    <div class="actions"><button class="btn sm" id="ceShuf">Mischen</button><button class="btn sm" id="ceRestart">Programm neu beginnen</button><button class="btn sm danger" id="ceClear">Alle entfernen</button>
    <button class="btn sm danger" id="ceDel">Sender löschen</button><button class="btn sm" id="cePlay">${ico("play")}Ansehen</button></div>
    <div style="max-height:420px;overflow-y:auto"><table class="tbl">${items.map((r, i) => `<tr><td style="color:var(--dim)">${i + 1}</td><td>${esc(r.title)}</td><td style="white-space:nowrap">${fmtDur(r.len)}</td>
    <td style="white-space:nowrap"><button class="btn sm" data-up="${i}" ${i ? "" : "disabled"}>↑</button> <button class="btn sm danger" data-rm="${r.row}">×</button></td></tr>`).join("")}</table></div></div>`;
  const re = () => editChannel(b, c, libs);
  const put = async body => { await api(`/api/channels/${c.id}`, { method: "PUT", body }); toast("Gespeichert", 1000); };
  $("#ceN").onchange = e => { c.name = e.target.value; put({ name: c.name }); };
  $("#ceNum").onchange = e => put({ number: e.target.value ? +e.target.value : null });
  bindSegs(box, (k, val) => put({ enabled: val ? 1 : 0 }));
  $("#ceLogo").onchange = async e => { const f = e.target.files[0]; if (!f) return; const r = await fetch(`/api/channels/${c.id}/logo`, { method: "POST", body: f }); toast(r.ok ? "Logo gespeichert" : (await r.json()).error); c.has_logo = true; };
  let qt;
  $("#ceQ").oninput = e => {
    clearTimeout(qt); const q = e.target.value.trim(); const res = $("#ceRes");
    if (q.length < 2) { res.classList.add("hidden"); return; }
    qt = setTimeout(async () => {
      const j = await api(`/api/search?q=${encodeURIComponent(q)}`);
      res.classList.remove("hidden");
      res.innerHTML = j.items.map(i => `<div data-add="${i.id}">${i.kind === "show" ? "📺 Serie (alle Folgen): " : i.kind === "episode" ? "▸ " + esc(i.show_title || "") + " – " : "🎬 "}${esc(i.title)}${i.year ? ` (${i.year})` : ""}${i.kind === "episode" ? ` S${i.season}E${i.episode}` : ""}</div>`).join("") || "<div>Nichts gefunden</div>";
      $$("[data-add]", res).forEach(d => d.onclick = async () => { const r = await api(`/api/channels/${c.id}/items`, { body: { ids: [+d.dataset.add] } }); toast(`${r.added} Titel hinzugefügt`); re(); });
    }, 300);
  };
  $$("[data-lib]", box).forEach(x => x.onclick = async () => { if (!confirm("Alle Titel dieser Bibliothek hinzufügen?")) return; const r = await api(`/api/channels/${c.id}/library`, { body: { lib: +x.dataset.lib } }); toast(`${r.added} Titel hinzugefügt`); re(); });
  $("#ceShuf").onclick = async () => { await api(`/api/channels/${c.id}/order`, { method: "PUT", body: { shuffle: true } }); re(); };
  $("#ceRestart").onclick = async () => { await put({ restart: true }); re(); };
  $("#ceClear").onclick = async () => { if (!confirm("Alle Titel aus dem Sender entfernen?")) return; await api(`/api/channels/${c.id}/items`, { method: "DELETE" }); re(); };
  $("#ceDel").onclick = async () => { if (!confirm(`Sender „${c.name}“ löschen?`)) return; await api(`/api/channels/${c.id}`, { method: "DELETE" }); setSender(b); };
  $("#cePlay").onclick = () => openChannel(c.id);
  $$("[data-rm]", box).forEach(x => x.onclick = async () => { await api(`/api/channels/${c.id}/items/${x.dataset.rm}`, { method: "DELETE" }); re(); });
  $$("[data-up]", box).forEach(x => x.onclick = async () => {
    const rows = items.map(r => r.row), i = +x.dataset.up; [rows[i - 1], rows[i]] = [rows[i], rows[i - 1]];
    await api(`/api/channels/${c.id}/order`, { method: "PUT", body: { rows } }); re();
  });
  box.scrollIntoView({ behavior: "smooth" });
}

S.ext.push({ route: "live", nav: "Live-TV", icon: "live", view: viewLive, settings: "Live-TV", settingsId: "live", admin: false, settingsView: setLive, settingsAdmin: true });
S.ext.push({ route: "guide", view: viewGuide });
S.ext.push({ route: "channels", nav: "Sender", icon: "chan", view: viewChannels, settings: "Eigene Sender", settingsId: "sender", settingsView: setSender, settingsAdmin: true });
