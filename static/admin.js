/* Bargain Bazaar: host screen client. All dynamic text uses textContent. */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  };
  const fmt = (n) => "₹" + Math.round(Number(n) || 0).toLocaleString("en-IN");
  const mmss = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.max(0, s) % 60).padStart(2, "0")}`;
  const rem = () => parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
  const store = (kind) => ({
    get(k) { try { return window[kind].getItem(k) || ""; } catch (e) { return ""; } },
    set(k, v) { try { window[kind].setItem(k, v); } catch (e) { /* ignore */ } },
  });
  const ses = store("sessionStorage"), loc = store("localStorage");

  const IDLE_LINES = [
    "Fixed price, boss. No bargaining!*", "Cheap, good, lasting. Pick any two!", "Come, come, next customer!",
    "Prices are fixed. Mostly.", "My family eats because of this shop. Please be gentle.", "Don't touch the display piece!",
    "Chai break after this customer.", "Haggle all you like. I have all day.", "Speak to me in any language, boss. Money speaks louder.",
  ];
  const idleTicks = () => [`🛍️ ${S.game ? S.game.shop_name : "The"} festive sale is ON`, "😎 Fixed prices* (*terms and conditions apply)",
                           "🪙 Be the first to strike a deal!", "🗣️ Haggle in any language you like"];
  const EV_MOOD = { rush: "pleased", tight: "annoyed" };
  const EV_RAIN = { rush: ["🪔", "🛍️", "🎁", "✨", "🪙"], tight: ["💸", "🧾", "😬", "📉"] };

  const S = { key: "", game: null, snap: null, offset: 0, rows: new Map(), chips: new Map(), seenDeals: new Set(), tickSig: "",
              tk: { start: Date.now(), dur: 40 }, queue: [], pumping: false, moodT: 0, lastLineAt: Date.now(), es: null,
              lastEv: Date.now(), joinUrl: "", qrFor: "", podiumShown: false, minsSet: false, ev: null, evTotal: 45, rainT: 0 };
  const keeperName = () => (S.game ? S.game.shopkeeper : "Shopkeeper");
  const restMood = () => (S.ev && EV_MOOD[S.ev.kind]) || "neutral";

  // Sound is optional: a missing or failing sound engine must never get in the way of the show.
  const sfx = {
    play(name, o) { try { return window.Sfx ? window.Sfx.play(name, o) : 0; } catch (e) { return 0; } },
    line(kind, mood) { try { if (window.Sfx) window.Sfx.line(kind, mood); } catch (e) { /* ignore */ } },
  };
  function wireSound() {
    if (!window.Sfx || wireSound.done) return;
    wireSound.done = true;
    try {
      window.Sfx.setup({ role: "host", key: "bz_sfx_host", def: (S.game.sound || {}).host });
      window.Sfx.bind($("#bSfx"), ["on", "soft", "off"], (b, st) => {
        b.textContent = st === "locked" ? "🔇 Click for sound" : st === "off" ? "🔇 Sound: Off" : st === "soft" ? "🔉 Sound: Soft" : "🔊 Sound: On";
      });
    } catch (e) { /* ignore */ }
  }
  function soundCheck() {
    const Sfx = window.Sfx, btn = $("#bSfxTest");
    if (!Sfx) return;
    if (btn.dataset.running) { Sfx.stopDemo(); return; }
    if (Sfx.level() === "off") { toast("Sound is switched off. Click the 🔊 button first."); return; }
    btn.dataset.running = "1";
    btn.textContent = "⏹ Stop sound check";
    Sfx.demo((s) => {
      toast(`${s.i}/${s.n}: ${s.label}`);
      Anna.mood($("#keeper"), s.mood || restMood());
    }).then((finished) => {
      delete btn.dataset.running;
      btn.textContent = "🎧 Sound check";
      Anna.mood($("#keeper"), restMood());
      if (finished) toast("Sound check done. If it is too loud or too quiet, use the 🔊 button (On / Soft / Off).");
    });
  }

  // ---------------------------------------------------------------- api and auth
  async function api(path, body) {
    const init = { method: body !== undefined ? "POST" : "GET", headers: { "X-Admin-Key": S.key } };
    if (body !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(body); }
    try { const r = await fetch(path, init); return await r.json(); } catch (e) { return { ok: false, error: "Server not reachable." }; }
  }

  function gate(msg) {
    $("#gate").classList.remove("hidden");
    if (msg) $("#gateMsg").textContent = msg;
    $("#gateKey").focus();
  }

  async function start() {
    const r = await api("/api/admin/info");
    if (!r.ok) { gate(r.error || "That key didn't work."); return; }
    $("#gate").classList.add("hidden");
    S.game = r.game;
    wireSound();
    // The server knows the real public link. A link typed into the join box (kept in this browser) is only a fallback for runs
    // where the server has no public link; otherwise a stale one from an earlier test could put a dead link on the QR code.
    S.joinUrl = (/localhost|127\.0\.0\.1/.test(r.join_url) && loc.get("bz_join")) || r.join_url;
    buildShop();
    $("#lobbyBudget").textContent = fmt(S.game.budget);
    $("#mins").value = S.game.duration_min;
    onSnapshot(r.snapshot);
    connect();
    refreshQR();
  }

  // ---------------------------------------------------------------- static scene
  function buildShop() {
    $("#shopSub").textContent = `${S.game.shop_name} · Festive Sale`;
    $("#signName").textContent = S.game.shop_name;
    $("#bubWho").textContent = S.game.shopkeeper;
    document.title = `${S.game.title}: Host screen`;
    const b = $("#bunting");
    b.textContent = "";
    const cols = ["#ff4d6d", "#ffc233", "#19c3b1", "#ff8a1f", "#8b6cff"];
    for (let i = 0; i < 14; i++) {
      const f = el("i");
      f.style.background = cols[i % cols.length];
      f.style.animationDelay = i * 0.17 + "s";
      b.append(f);
    }
    const sh = $("#shelves");
    sh.textContent = "";
    for (const it of S.game.items) {
      const d = el("div", "slot");
      d.dataset.id = it.id;
      d.append(el("span", "em", it.emoji), el("span", "tag", fmt(it.list)), el("span", "sold", "\u00a0"));
      sh.append(d);
    }
  }

  // ---------------------------------------------------------------- live connection
  function connect() {
    if (S.es) { try { S.es.close(); } catch (e) { /* ignore */ } }
    const es = new EventSource("/api/admin/stream?key=" + encodeURIComponent(S.key));
    S.es = es;
    es.addEventListener("snapshot", (e) => { S.lastEv = Date.now(); onSnapshot(JSON.parse(e.data)); });
    es.addEventListener("fx", (e) => { S.lastEv = Date.now(); onFx(JSON.parse(e.data)); });
  }
  setInterval(async () => {
    if (S.game && Date.now() - S.lastEv > 15000) {
      const r = await api("/api/admin/info");
      if (r.ok) onSnapshot(r.snapshot);
      connect();
    }
  }, 6000);

  function onSnapshot(s) {
    const prev = S.snap;
    S.snap = s;
    S.offset = s.now - Date.now() / 1000;
    if (prev && prev.status !== "lobby" && s.status === "lobby") { clearRows(); S.podiumShown = false; S.seenDeals.clear(); S.bell60 = undefined; }
    renderHeader();
    renderShop();
    renderEvent();
    renderControls();
    if (s.status === "lobby") renderLobby(); else renderBoard();
    renderTrades();
    renderLines();
    renderTicker();
    tickClock();
    if (s.status === "ended") {
      if (!S.podiumShown) { S.podiumShown = true; renderPodium(); $("#podium").classList.remove("hidden"); confetti(70); }
      else if (!$("#podium").classList.contains("hidden")) renderPodium();
    } else {
      $("#podium").classList.add("hidden");
    }
  }

  function clearRows() {
    for (const r of S.rows.values()) r.el.remove();
    S.rows.clear();
    for (const c of S.chips.values()) c.remove();
    S.chips.clear();
  }

  // ---------------------------------------------------------------- header, clock, controls
  function renderHeader() {
    const s = S.snap;
    const pill = $("#statusPill");
    pill.className = "status " + s.status;
    pill.querySelector("span").textContent = s.status === "lobby" ? "LOBBY" : s.status === "live" ? "LIVE" : "CLOSED";
    $("#stPlayers").textContent = s.players.length;
    $("#stDeals").textContent = s.stats.deals;
    $("#stDone").textContent = s.stats.completed;
    $("#stTricks").textContent = s.stats.tricks;
    const u = $("#joinUrl");
    u.textContent = S.joinUrl.replace(/^https?:\/\//, "");
    u.classList.toggle("warn", /localhost|127\.0\.0\.1/.test(S.joinUrl));
    $("#joinUrlBig").textContent = S.joinUrl.replace(/^https?:\/\//, "");
  }

  function tickClock() {
    const s = S.snap;
    if (!s) return;
    const c = $("#clock");
    if (s.status === "lobby") c.textContent = mmss(s.duration);
    else if (s.status === "ended") c.textContent = "00:00";
    else if (!s.ends_at) c.textContent = "∞";
    else {
      const left = Math.max(0, Math.round(s.ends_at - (Date.now() / 1000 + S.offset)));
      c.textContent = mmss(left);
      c.parentElement.classList.toggle("urgent", left <= 60);
      if (S.bell60 === undefined) S.bell60 = left <= 60;               // a page opened inside the last minute stays quiet
      else if (left > 75) S.bell60 = false;                            // (more time was added: ring again for the new last minute)
      else if (left <= 60 && left > 0 && !S.bell60 && s.duration >= 150) { S.bell60 = true; sfx.play("bell"); }
    }
  }
  setInterval(tickClock, 250);

  function renderControls() {
    const s = S.snap, st = s.status;
    document.body.dataset.status = st;
    $("#bStart").classList.toggle("hidden", st !== "lobby");
    $("#minsWrap").classList.toggle("hidden", st !== "lobby");
    $("#bExtend").classList.toggle("hidden", st !== "live");
    $("#bEnd").classList.toggle("hidden", st !== "live");
    $("#bResults").classList.toggle("hidden", st === "lobby");
    $("#bPodium").classList.toggle("hidden", st !== "ended");
    $("#bReveal").textContent = s.reveal ? "🔓 Prices shown" : "🔒 Prices hidden";
    $("#bRush").classList.toggle("hidden", st !== "live");
    $("#bTight").classList.toggle("hidden", st !== "live");
    $("#bSfxTest").classList.toggle("hidden", st === "live");
    $("#bClearEv").classList.toggle("hidden", !(st === "live" && S.ev));
    const a = s.ai, chip = $("#aiChip"), model = a.model ? ` · ${a.model}` : "";
    chip.textContent = a.muted
      ? "AI replies: switched OFF (ready-made lines only)"
      : a.mode === "ai"
        ? `AI replies: ${a.healthy ? "live" : "degraded"}${model}${a.avg_ms ? ` · ${(a.avg_ms / 1000).toFixed(1)}s` : ""} · ${a.ai_replies} AI / ${a.fallback_replies} ready-made${a.recent_fail_pct ? ` · ${a.recent_fail_pct}% recent fails` : ""}`
        : "AI replies: ready-made lines only";
    chip.className = "ai " + (a.mode === "ai" && a.healthy ? "ok" : "bad");
    $("#bAi").textContent = a.muted ? "🤖 AI replies: OFF" : a.mode === "ai" ? "🤖 AI replies: ON" : "🤖 AI replies: n/a";
    $("#bAi").disabled = a.mode !== "ai" && !a.muted;
  }

  // ---------------------------------------------------------------- shop scene
  function renderShop() {
    const items = S.snap.stats.items;
    document.querySelectorAll(".slot").forEach((slot) => {
      const st = items.find((x) => x.id === slot.dataset.id);
      slot.querySelector(".sold").textContent = st && st.sold ? `${st.sold} sold · avg -${st.avg_pct}%` : "\u00a0";
    });
  }

  function showLine(ev) {
    $("#bubWho").textContent = ev.player ? `${keeperName()} → ${ev.player} · ${ev.emoji} ${ev.item}` : keeperName();
    $("#bubTxt").textContent = ev.text;
    const b = $("#bubble");
    b.classList.remove("pop"); void b.offsetWidth; b.classList.add("pop");
    Anna.mood($("#keeper"), ev.mood || restMood());
    if (ev.player && (ev.kind !== "DEAL" || ev.mood === "sobbing")) sfx.line(ev.kind, ev.mood);     // a plain sale is the register's job; a painful one gets the sad trombone
    clearTimeout(S.moodT);
    S.moodT = setTimeout(() => Anna.mood($("#keeper"), restMood()), 6500);
  }
  function pump() {
    const ev = S.queue.shift();
    if (!ev) { S.pumping = false; return; }
    S.pumping = true;
    showLine(ev);
    setTimeout(pump, 2600);
  }
  function enqueue(ev) {
    S.queue.push(ev);
    if (S.queue.length > 4) {
      const i = S.queue.findIndex((x) => x.kind !== "DEAL" && x.kind !== "TRICK" && x.kind !== "RAISE");
      S.queue.splice(i >= 0 ? i : 0, 1);
    }
    if (!S.pumping) pump();
  }
  setInterval(() => {
    if (!S.pumping && Date.now() - S.lastLineAt > 9000) {
      S.lastLineAt = Date.now();
      showLine({ text: IDLE_LINES[Math.floor(Math.random() * IDLE_LINES.length)], mood: "neutral" });
    }
  }, 3000);

  // ---------------------------------------------------------------- leaderboard
  function makeRow() {
    const e = el("div", "row");
    const rk = el("div", "rk"), nm = el("div", "nm"), bag = el("div", "bag"), amt = el("div", "amt");
    const spans = S.game.items.map((it) => { const s = el("span", "", it.emoji); bag.append(s); return s; });
    const v = el("span", "v"), small = el("small");
    amt.append(v, small);
    e.append(rk, nm, bag, amt);
    return { el: e, rk, nm, spans, v, small, last: "" };
  }

  function renderBoard() {
    const box = $("#rows"), s = S.snap;
    box.classList.remove("hidden");
    $("#lobbyBox").classList.add("hidden");
    $("#boardName").textContent = "🏆 Leaderboard";
    const rowH = 4.65 * rem();
    const max = Math.max(4, Math.floor(box.clientHeight / rowH));
    const list = s.players.slice(0, max);
    $("#boardSub").textContent = s.players.length > max ? `top ${max} of ${s.players.length}` : `${s.players.length} shoppers`;
    let empty = box.querySelector(".empty");
    if (!list.length) {
      if (!empty) { empty = el("div", "empty", "Waiting for the first shopper to walk in…"); box.append(empty); }
    } else if (empty) empty.remove();
    const seen = new Set();
    list.forEach((p, i) => {
      let r = S.rows.get(p.id);
      if (!r) {
        r = makeRow();
        S.rows.set(p.id, r);
        box.append(r.el);
        r.el.style.transition = "none";
        r.el.style.transform = `translateY(${i * rowH + 36}px)`;
        r.el.style.opacity = "0";
        r.el.getBoundingClientRect();
        r.el.style.transition = "";
      }
      r.el.style.transform = `translateY(${i * rowH}px)`;
      r.el.style.opacity = "1";
      for (const k of ["r1", "r2", "r3"]) r.el.classList.toggle(k, i < 3 && k === "r" + (i + 1));
      r.el.classList.toggle("done", p.completed);
      r.rk.textContent = p.rank;
      r.nm.textContent = p.name;
      S.game.items.forEach((it, k) => r.spans[k].classList.toggle("on", p.bought.includes(it.id)));
      r.v.textContent = p.n ? fmt(p.spent) : "–";
      r.small.textContent = p.n ? `-${p.saved_pct}% off` : "";
      const sig = p.n + ":" + p.spent;
      if (r.last && r.last !== sig) { r.el.classList.add("flash"); setTimeout(() => r.el.classList.remove("flash"), 1400); }
      r.last = sig;
      seen.add(p.id);
    });
    for (const [id, r] of S.rows) {
      if (!seen.has(id)) { const e = r.el; e.style.opacity = "0"; setTimeout(() => e.remove(), 600); S.rows.delete(id); }
    }
  }

  function renderLobby() {
    const s = S.snap;
    $("#rows").classList.add("hidden");
    $("#lobbyBox").classList.remove("hidden");
    $("#boardName").textContent = "🛍️ Shoppers inside";
    $("#boardSub").textContent = `${s.players.length} joined`;
    const box = $("#chips"), ids = new Set(s.players.map((p) => p.id));
    for (const [id, c] of S.chips) if (!ids.has(id)) { c.remove(); S.chips.delete(id); }
    for (const p of s.players.slice(-90)) {
      if (!S.chips.has(p.id)) { const c = el("span", "chip", p.name); box.append(c); S.chips.set(p.id, c); }
    }
  }

  // ---------------------------------------------------------------- trades, overheard, ticker
  function renderTrades() {
    const ul = $("#trades"), deals = S.snap.deals.slice(0, 8);
    ul.textContent = "";
    if (!deals.length) { ul.append(el("li", "muted", `No deals yet. ${keeperName()} is smiling.`)); return; }
    for (const d of deals) {
      const key = d.pid + d.item_id;
      const li = el("li", S.seenDeals.has(key) ? "" : "new");
      S.seenDeals.add(key);
      const who = el("span", "who", d.player);
      who.append(el("small", "", d.item_name));
      const pct = el("span", "pct", "-" + d.discount_pct + "%");
      if (d.price != null) pct.append(el("small", "", fmt(d.price)));
      li.append(el("span", "em", d.emoji), who, pct);
      ul.append(li);
    }
  }

  function renderLines() {
    const ul = $("#lines");
    ul.textContent = "";
    const lines = S.snap.lines.slice(0, 6);
    if (!lines.length) { ul.append(el("li", "muted", "It's quiet. Too quiet.")); return; }
    for (const l of lines) {
      const li = el("li");
      li.append(el("b", "", l.player + " "), document.createTextNode(`${l.emoji} “${l.text}”`));
      ul.append(li);
    }
  }

  function fillTicker(track, items, reps) {
    track.textContent = "";
    for (let c = 0; c < 2 * reps; c++) for (const t of items) track.append(el("span", "", t));
  }
  function renderTicker() {
    const deals = S.snap.deals;
    const items = deals.length
      ? deals.slice(0, 30).map((d) => `${d.emoji} ${d.player} bagged ${d.item_name} at ${d.discount_pct}% OFF${d.price != null ? " (" + fmt(d.price) + ")" : ""}`)
      : idleTicks();
    const sig = items.join("|");
    if (sig === S.tickSig) return;
    S.tickSig = sig;
    const track = $("#tkTrack"), view = track.parentElement.clientWidth;
    fillTicker(track, items, 1);
    const reps = Math.max(1, Math.ceil(view / (track.scrollWidth / 2 || 1)));
    if (reps > 1) fillTicker(track, items, reps);
    const half = track.scrollWidth / 2;
    const dur = Math.max(20, half / (150 * rem() / 16));
    const frac = (((Date.now() - S.tk.start) / 1000) % S.tk.dur) / S.tk.dur;
    track.style.setProperty("--dur", dur + "s");
    track.style.animation = "none"; void track.offsetWidth; track.style.animation = "";
    track.style.animationDelay = -(frac * dur) + "s";
    S.tk = { start: Date.now() - frac * dur * 1000, dur };
  }

  // ---------------------------------------------------------------- market events (the whole shop's mood swings for a short while)
  function rainDrop(list) {
    const layer = $("#fxLayer"), w = layer.clientWidth, h = layer.clientHeight;
    const s = el("span", "coin", list[Math.floor(Math.random() * list.length)]);
    s.style.left = Math.random() * Math.max(10, w - 40) + "px";
    s.style.top = "0px";
    s.style.fontSize = 1.5 * rem() + Math.random() * 1.4 * rem() + "px";
    layer.append(s);
    s.animate([{ transform: "translateY(-30px) rotate(0deg)", opacity: 0 },
               { transform: `translateY(${h * 0.12}px) rotate(30deg)`, opacity: 1, offset: 0.12 },
               { transform: `translateY(${h}px) rotate(${(Math.random() - 0.5) * 360}deg)`, opacity: 0.85 }],
              { duration: 3200 + Math.random() * 1800, easing: "ease-in" }).onfinish = () => s.remove();
  }

  function startEventFx(m) {
    S.ev = m;
    S.evTotal = Math.max(1, m.until - (Date.now() / 1000 + S.offset));
    const inner = $("#evInner"), txt = el("div", "evtxt");
    txt.append(el("b", "", m.title), el("small", "", m.text));
    inner.className = "evinner " + m.kind;
    inner.textContent = "";
    inner.append(el("span", "evem", m.emoji), txt, el("span", "evtime", ""), el("i", "evbar"));
    $("#evStrip").classList.add("on");
    const shop = $("#shop");
    shop.classList.remove("ev-rush", "ev-tight");
    shop.classList.add("ev-" + m.kind);
    if (m.kind === "rush") { confetti(24); coins(14); }
    Anna.mood($("#keeper"), restMood());
    clearInterval(S.rainT);
    S.rainT = setInterval(() => rainDrop(EV_RAIN[m.kind] || EV_RAIN.rush), 520);
  }

  function endEventFx() {
    S.ev = null;
    clearInterval(S.rainT);
    $("#evStrip").classList.remove("on");
    $("#shop").classList.remove("ev-rush", "ev-tight");
    Anna.mood($("#keeper"), "neutral");
  }

  function renderEvent() {
    const m = S.snap && S.snap.market;
    const live = S.snap && S.snap.status === "live";
    if (m && live && m.until - (Date.now() / 1000 + S.offset) > 0) {
      if (!S.ev || S.ev.kind !== m.kind || S.ev.until !== m.until) startEventFx(m);
    } else if (S.ev) {
      endEventFx();
    }
    tickEvent();
  }

  function tickEvent() {
    if (!S.ev) return;
    const left = S.ev.until - (Date.now() / 1000 + S.offset);
    if (left <= 0) { endEventFx(); renderControls(); return; }
    const t = document.querySelector("#evInner .evtime"), bar = document.querySelector("#evInner .evbar");
    if (t) t.textContent = Math.ceil(left) + "s";
    if (bar) bar.style.width = Math.max(0, Math.min(100, (100 * left) / S.evTotal)) + "%";
  }
  setInterval(tickEvent, 250);

  // ---------------------------------------------------------------- effects
  function onFx(ev) {
    if (ev.type === "line") { S.lastLineAt = Date.now(); enqueue(ev); }
    else if (ev.type === "deal") { dealFx(ev); sfx.play((ev.discount_pct || 0) >= 22 ? "dealBig" : "deal"); }
    else if (ev.type === "complete") { banner(`🎉 ${ev.name} filled the whole bag!`); confetti(40); sfx.play("tada"); }
    else if (ev.type === "join") sfx.play("door");
    else if (ev.type === "event" && ev.kind) sfx.play(ev.kind === "rush" ? "rush" : "tight");
    else if (ev.type === "status" && ev.status === "live") { S.bell60 = false; sfx.play("open"); }
    else if (ev.type === "status" && ev.status === "ended") { sfx.play("close"); setTimeout(() => sfx.play("fanfare"), 1100); }
  }

  function dealFx(ev) {
    coins(12);
    const p = el("div", "fx-pop", `${ev.emoji} -${ev.discount_pct}%!`);
    $("#fxLayer").append(p);
    setTimeout(() => p.remove(), 1900);
    const slot = document.querySelector(`.slot[data-id="${ev.item_id}"]`);
    if (slot) { slot.classList.remove("pulse"); void slot.offsetWidth; slot.classList.add("pulse"); }
  }

  function coins(n) {
    const layer = $("#fxLayer"), w = layer.clientWidth, h = layer.clientHeight;
    for (let i = 0; i < n; i++) {
      const c = el("span", "coin", i % 3 === 0 ? "💰" : "🪙");
      c.style.left = w * (0.3 + Math.random() * 0.4) + "px";
      c.style.top = h - 9 * rem() + "px";
      layer.append(c);
      const dx = (Math.random() - 0.5) * w * 0.6, dy = -(h * (0.25 + Math.random() * 0.35));
      c.animate([{ transform: "translate(0,0) scale(.6)", opacity: 1 }, { transform: `translate(${dx}px,${dy}px) scale(1.2) rotate(${Math.random() * 720}deg)`, opacity: 0 }],
                { duration: 1100 + Math.random() * 600, easing: "cubic-bezier(.2,.8,.3,1)" }).onfinish = () => c.remove();
    }
  }

  function confetti(n) {
    const em = ["🎉", "🪙", "✨", "💰", "🛍️", "🎊"];
    for (let i = 0; i < n; i++) {
      const s = el("span", "fly", em[i % em.length]);
      s.style.left = Math.random() * 100 + "vw";
      s.style.top = "-6vh";
      s.style.fontSize = 1.4 * rem() + Math.random() * 1.6 * rem() + "px";
      s.style.zIndex = "70";
      document.body.append(s);
      s.animate([{ transform: "translate(0,0) rotate(0)", opacity: 1 },
                 { transform: `translate(${(Math.random() - 0.5) * 300}px, 108vh) rotate(${(Math.random() - 0.5) * 720}deg)`, opacity: 0.9 }],
                { duration: 2600 + Math.random() * 2600, delay: Math.random() * 900, easing: "ease-in" }).onfinish = () => s.remove();
    }
  }

  function banner(text) {
    const b = $("#banner");
    b.textContent = text;
    b.classList.remove("hidden");
    clearTimeout(banner.t);
    banner.t = setTimeout(() => b.classList.add("hidden"), 4200);
  }

  function toast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    t.classList.remove("hidden");
    clearTimeout(toast.t);
    toast.t = setTimeout(() => t.classList.add("hidden"), 3600);
  }

  // ---------------------------------------------------------------- podium
  function renderPodium() {
    const s = S.snap, box = $("#podium");
    box.textContent = "";
    box.append(el("h1", "", "THE BAZAAR IS CLOSED"),
               el("p", "sub", `${s.players.length} shoppers · ${s.stats.deals} deals · ${s.stats.completed} full bags`));
    const steps = el("div", "steps");
    s.players.slice(0, 3).forEach((p, i) => {
      const st = el("div", `step p${i + 1}`);
      st.append(el("div", "medal", ["🥇", "🥈", "🥉"][i]), el("div", "pn", p.name), el("div", "pt", p.n ? fmt(p.spent) : "–"));
      const bag = el("div", "bag");
      for (const it of S.game.items) { const sp = el("span", "", it.emoji); if (!p.bought.includes(it.id)) sp.style.opacity = ".2"; bag.append(sp); }
      st.append(bag, el("div", "ps", p.completed ? `${p.saved_pct}% below sticker` : `${p.n}/${S.game.items.length} items`));
      steps.append(st);
    });
    box.append(steps);
    const aw = el("div", "awards2");
    for (const a of s.awards || []) {
      const c = el("div", "award2");
      c.append(el("span", "em", a.emoji), el("b", "", a.title), el("span", "who", a.name), el("div", "muted", a.detail));
      aw.append(c);
    }
    box.append(aw);
    const close = el("button", "btn ghost", "Back to the board");
    close.style.marginTop = "1.4rem";
    close.onclick = () => $("#podium").classList.add("hidden");
    box.append(close);
  }

  // ---------------------------------------------------------------- modals and actions
  function closeModal() { $("#modal").classList.add("hidden"); }
  function confirmBox(title, text, yesLabel, onYes, danger) {
    const card = $("#modalCard");
    card.textContent = "";
    card.append(el("h2", "", title), el("p", "muted", text));
    const row = el("div", "row2"), no = el("button", "btn ghost", "Cancel"), yes = el("button", "btn" + (danger ? " red" : ""), yesLabel);
    no.onclick = closeModal;
    yes.onclick = () => { closeModal(); onYes(); };
    row.append(no, yes);
    card.append(row);
    $("#modal").classList.remove("hidden");
    yes.focus();
  }

  function playersModal() {
    const card = $("#modalCard");
    card.textContent = "";
    card.append(el("h2", "", `Players (${S.snap.players.length})`),
                el("p", "muted", "Remove someone if their name or behaviour is a problem. They can rejoin with a new name."));
    const ul = el("ul", "plist");
    for (const p of S.snap.players) {
      const li = el("li");
      const b = el("button", "btn red", "Remove");
      b.onclick = async () => { await api("/api/admin/kick", { pid: p.id }); li.remove(); };
      li.append(el("span", "", p.name), el("span", "muted", `${p.n}/${S.game.items.length} · ${fmt(p.spent)}`), b);
      ul.append(li);
    }
    card.append(ul);
    const row = el("div", "row2"), close = el("button", "btn", "Close");
    close.onclick = closeModal;
    row.append(close);
    card.append(row);
    $("#modal").classList.remove("hidden");
  }

  async function download() {
    try {
      const r = await fetch("/api/admin/export", { headers: { "X-Admin-Key": S.key } });
      const blob = await r.blob();
      const a = el("a");
      a.href = URL.createObjectURL(blob);
      a.download = "bargain-bazaar-results.json";
      document.body.append(a);
      a.click();
      a.remove();
    } catch (e) { toast("Could not download results."); }
  }

  async function refreshQR() {
    const url = S.joinUrl;
    if (!url || S.qrFor === url) return;
    try {
      const r = await fetch("/api/admin/qr?url=" + encodeURIComponent(url), { headers: { "X-Admin-Key": S.key } });
      if (!r.ok) return;
      const svg = await r.text();
      S.qrFor = url;
      const src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
      for (const box of [$("#qrSmall"), $("#qrBig")]) {
        box.textContent = "";
        const img = el("img");
        img.src = src;
        img.alt = "QR code to join";
        box.append(img);
      }
    } catch (e) { /* no QR is fine; the link is shown as text */ }
  }

  $("#joinBox").onclick = () => {
    const u = window.prompt("Public link players should use (this builds the QR code):", S.joinUrl);
    if (u && /^https?:\/\/\S+$/.test(u.trim())) { S.joinUrl = u.trim(); loc.set("bz_join", S.joinUrl); renderHeader(); refreshQR(); }
  };
  $("#bStart").onclick = async () => {
    const r = await api("/api/admin/start", { minutes: parseInt($("#mins").value, 10) || null });
    if (!r.ok) toast(r.error || "Could not start.");
  };
  $("#bExtend").onclick = () => api("/api/admin/extend", { seconds: 120 });
  $("#bEnd").onclick = () => confirmBox("End the game now?", "The shop closes for everyone and the final ranking is shown.", "Yes, close the shop", () => api("/api/admin/end", {}), true);
  $("#bNew").onclick = () => confirmBox("Start a new game?", "This removes all shoppers and results. Everyone has to join again.", "Yes, reset everything", () => api("/api/admin/reset", {}), true);
  $("#bReveal").onclick = () => api("/api/admin/reveal", { on: !S.snap.reveal });
  $("#bRush").onclick = () => api("/api/admin/event", { kind: "rush" });
  $("#bTight").onclick = () => api("/api/admin/event", { kind: "tight" });
  $("#bClearEv").onclick = () => api("/api/admin/event", { kind: "clear" });
  $("#bTest").onclick = async () => {
    toast(`Testing ${keeperName()}'s AI replies…`);
    const r = await api("/api/admin/test-ai", {});
    toast(r.ok ? `✅ AI replies ready (${(r.ms / 1000).toFixed(1)}s)` : `⚠ ${r.message || r.error}: the ready-made lines will be used`);
  };
  $("#bPlayers").onclick = playersModal;
  $("#bSfxTest").onclick = soundCheck;
  $("#bAi").onclick = () => api("/api/admin/ai", { on: !!S.snap.ai.muted });
  $("#bResults").onclick = download;
  $("#bPodium").onclick = () => { renderPodium(); $("#podium").classList.remove("hidden"); };
  $("#bFull").onclick = () => { if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen(); };
  $("#gateGo").onclick = () => { S.key = $("#gateKey").value.trim(); ses.set("bz_admin", S.key); start(); };
  $("#gateKey").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#gateGo").click(); });
  document.addEventListener("keydown", (e) => {
    if (e.target && /INPUT|TEXTAREA/.test(e.target.tagName)) return;
    if (e.key === "h" || e.key === "H") document.body.classList.toggle("hide-ui");
    if (e.key === "m" || e.key === "M") $("#bSfx").click();
    if (e.key === "Escape") closeModal();
  });

  // ---------------------------------------------------------------- boot
  const q = new URLSearchParams(location.search).get("key");
  if (q) { ses.set("bz_admin", q); history.replaceState(null, "", location.pathname); }
  S.key = ses.get("bz_admin");
  if (S.key) start(); else gate();
})();
