/* Bargain Bazaar: player client. All user-supplied text is inserted with textContent only. */
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
  const mmss = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  const ls = {
    get(k) { try { return localStorage.getItem(k) || ""; } catch (e) { return ""; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } },
    del(k) { try { localStorage.removeItem(k); } catch (e) { /* private mode */ } },
  };
  // Open the page as /?p=2 (any short label) to be a separate player in the same browser: handy for trying the game alone.
  const NS = (new URLSearchParams(location.search).get("p") || "").replace(/[^\w-]/g, "").slice(0, 12);
  const key = (k) => (NS ? `${k}_${NS}` : k);
  const S = { token: ls.get(key("bz_token")), game: null, me: null, state: null, offset: 0, cur: null, sending: false, glow: null,
              lastStatus: null, es: null, lastEv: Date.now() };
  const N = () => (S.game ? S.game.items.length : 6);
  const itemOf = (id) => S.game.items.find((i) => i.id === id);

  // Sound is optional: a missing or failing sound engine must never get in the way of the game.
  const sfx = {
    play(name, o) { try { return window.Sfx ? window.Sfx.play(name, o) : 0; } catch (e) { return 0; } },
    reply(r) { try { if (window.Sfx) window.Sfx.reply(r); } catch (e) { /* ignore */ } },
  };
  function wireSound() {
    if (!window.Sfx || wireSound.done || !S.game) return;
    wireSound.done = true;
    try {
      window.Sfx.setup({ role: "player", key: "bz_sfx", def: (S.game.sound || {}).players });
      const paint = (b, st) => {
        b.textContent = st === "off" ? "🔇" : st === "soft" ? "🔉" : "🔊";
        b.title = st === "off" ? "Sounds are off. Tap to switch them on." : st === "locked" ? "Tap here to switch Raju Anna's sounds on." : "Sounds are on. Tap to switch them off.";
      };
      for (const id of ["#btnSfx", "#btnSfx2"]) window.Sfx.bind($(id), ["on", "off"], paint);
    } catch (e) { /* ignore */ }
  }

  // ---------------------------------------------------------------- api
  async function api(path, body) {
    const init = { method: body ? "POST" : "GET", headers: { "X-Token": S.token } };
    if (body) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(body); }
    let r;
    try { r = await fetch(path, init); } catch (e) { return { ok: false, code: "net", error: "No network. Check your connection and try again." }; }
    let j;
    try { j = await r.json(); } catch (e) { j = { ok: false, code: "bad", error: "Something went wrong. Try again." }; }
    if (j && j.code === "auth") forget("Please rejoin the bazaar.");
    return j;
  }

  function show(id) {
    for (const s of ["sJoin", "sLobby", "sShop", "sEnd"]) $("#" + s).classList.toggle("hidden", s !== id);
    window.scrollTo(0, 0);
  }

  function forget(msg) {
    S.token = ""; S.me = null; ls.del(key("bz_token"));
    closeSheet();
    $("#top").classList.add("hidden");
    show("sJoin");
    $("#joinErr").textContent = msg || "";
  }

  // ---------------------------------------------------------------- boot and join
  function applyGame() {
    if (!S.game) return;
    document.querySelectorAll(".howBudget").forEach((e) => { e.textContent = fmt(S.game.budget); });
    document.querySelectorAll(".keeperName").forEach((e) => { e.textContent = S.game.shopkeeper; });
    document.querySelectorAll(".keeperUpper").forEach((e) => { e.textContent = S.game.shopkeeper.toUpperCase(); });
    document.querySelectorAll(".keeperShop").forEach((e) => { e.textContent = S.game.shop_name; });
    $("#shopName").textContent = S.game.shop_name;
    document.title = S.game.title + (NS ? ` [${NS}]` : "");
    wireSound();
  }

  // Same rule as the server (which has the last word): at least 4 characters, and not one letter repeated.
  function nameProblem(name) {
    const core = [...name].filter((ch) => /[\p{L}\p{M}\p{N}]/u.test(ch)).length;
    const letters = [...name].filter((ch) => /\p{L}/u.test(ch)).length;
    const distinct = new Set([...name.toLowerCase().replace(/\s/g, "")]).size;
    if (core < 4 || letters < 2 || distinct < 2) return "Please use at least 4 characters for your name.";
    return "";
  }

  async function boot() {
    $("#name").value = ls.get(key("bz_name"));
    const pub = await api("/api/public");
    if (pub.ok) { S.game = pub.game; S.state = pub.state; S.lastStatus = pub.state.status; applyGame(); }
    if (S.token) {
      const r = await api("/api/me");
      if (r.ok) { S.me = r.me; S.game = r.game; S.state = r.state; S.lastStatus = r.state.status; applyGame(); }
    }
    connect();
    route();
  }

  async function join() {
    const btn = $("#btnJoin");
    $("#joinErr").textContent = "";
    const name = $("#name").value.trim();
    const bad = nameProblem(name);
    if (bad) { $("#joinErr").textContent = bad; $("#name").focus(); return; }
    btn.disabled = true;
    ls.set(key("bz_name"), name);
    const r = await api("/api/join", { name });
    btn.disabled = false;
    if (!r.ok) { $("#joinErr").textContent = r.error || "Could not join. Try again."; return; }
    S.token = r.token; ls.set(key("bz_token"), r.token);
    S.game = r.game; S.me = r.me; S.state = r.state; S.lastStatus = r.state.status;
    applyGame();
    connect();
    route();
    if (r.state.status === "live") {
      const left = secsLeft();
      toast(left ? `The game is already on. ${mmss(left)} left, go go go!` : "The game is already on. Go go go!");
    }
  }

  function route() {
    const st = S.state ? S.state.status : "lobby";
    renderEvent();
    if (!S.me) {
      $("#top").classList.add("hidden");
      if (st === "ended") { renderEnd(); show("sEnd"); return; }        // latecomers can still see how it went
      show("sJoin");
      return;
    }
    $("#top").classList.remove("hidden");
    renderTop();
    if (st === "ended") { closeSheet(); renderEnd(); show("sEnd"); }
    else if (st === "lobby") { closeSheet(); renderLobby(); show("sLobby"); }
    else { renderShelf(); renderLive(); show("sShop"); }
  }

  // ---------------------------------------------------------------- live updates (SSE with watchdog and polling fallback)
  function connect() {
    if (S.es) { try { S.es.close(); } catch (e) { /* ignore */ } }
    const es = new EventSource("/api/stream");
    S.es = es;
    es.addEventListener("snapshot", (e) => { S.lastEv = Date.now(); onSnapshot(JSON.parse(e.data)); });
    es.addEventListener("fx", (e) => { S.lastEv = Date.now(); onFx(JSON.parse(e.data)); });
    es.onopen = () => { S.lastEv = Date.now(); if (S.token && S.me) refreshMe(); };
  }

  setInterval(async () => {
    if (Date.now() - S.lastEv > 15000) {
      const pub = await api("/api/public");
      if (pub.ok) onSnapshot(pub.state);
      connect();
    }
  }, 6000);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) { refreshMe(); if (Date.now() - S.lastEv > 8000) connect(); }
  });

  function onSnapshot(s) {
    S.state = s;
    S.offset = s.now - Date.now() / 1000;
    renderEvent();
    if (!S.me) {
      if (S.lastStatus !== s.status) { S.lastStatus = s.status; route(); }
      return;
    }
    if (s.status !== S.lastStatus) {
      S.lastStatus = s.status;
      refreshMe().then(route);
    } else {
      renderTop();
      renderLive();
    }
  }

  function onFx(ev) {
    if (ev.type === "reset") forget(`${S.game ? S.game.shopkeeper : "The shopkeeper"} started a fresh game. Join again!`);
    else if (S.me && ev.type === "status") sfx.play(ev.status === "live" ? "open" : ev.status === "ended" ? "close" : "");
    else if (S.me && ev.type === "event" && ev.kind) sfx.play(ev.kind === "rush" ? "rush" : "tight");
  }

  // The running market event (a short, announced mood swing of the whole shop), shown to everyone who has joined.
  function renderEvent() {
    const m = S.state && S.state.market;
    const left = m ? Math.round(m.until - (Date.now() / 1000 + S.offset)) : 0;
    const on = !!(m && left > 0 && S.me && S.state.status === "live");
    document.querySelectorAll("[data-eventbar]").forEach((bar) => {
      bar.classList.toggle("hidden", !on);
      if (!on) return;
      bar.className = "eventbar " + m.kind;
      bar.textContent = "";
      bar.append(el("b", "", `${m.emoji} ${m.title} · ${left}s`), el("small", "", m.text));
    });
  }
  setInterval(renderEvent, 1000);

  async function refreshMe() {
    if (!S.token) return;
    const r = await api("/api/me");
    if (r.ok) { S.me = r.me; S.game = r.game; renderTop(); if (S.cur) renderSheet(); }
  }

  // ---------------------------------------------------------------- top bar and timer
  function secsLeft() {
    const s = S.state;
    if (!s || !s.ends_at) return null;
    return Math.max(0, Math.round(s.ends_at - (Date.now() / 1000 + S.offset)));
  }
  function tickTimer() {
    const s = S.state, t = $("#timer");
    if (!s) return;
    if (s.status === "lobby") t.textContent = "soon";
    else if (s.status === "ended") t.textContent = "closed";
    else {
      const left = secsLeft();
      t.textContent = left === null ? "open" : mmss(left);
      $("#timerPill").classList.toggle("urgent", left !== null && left <= 60);
    }
  }
  setInterval(tickTimer, 500);

  function renderTop() {
    if (!S.me) return;
    $("#wallet").textContent = fmt(S.me.wallet);
    const rk = S.state && S.state.ranks ? S.state.ranks[S.me.id] : S.me.rank;
    const of = S.state ? S.state.n_players : S.me.of;
    $("#rank").textContent = rk && S.state && S.state.status !== "lobby" ? `#${rk}/${of}` : "–";
    tickTimer();
  }

  // ---------------------------------------------------------------- lobby, shelf, boards
  function renderLobby() {
    $("#lobbyName").textContent = S.me.name;
    $("#lobbyN").textContent = S.state ? S.state.n_players : 1;
  }

  function renderShelf() {
    const box = $("#shelf");
    box.textContent = "";
    for (const it of S.game.items) {
      const n = S.me.items[it.id];
      const b = el("button", "item" + (n.status === "sold" ? " sold" : n.status === "final" ? " final" : n.rounds > 0 || n.chat.length ? " active" : ""));
      b.type = "button";
      b.append(el("span", "em", it.emoji), el("span", "nm", it.name));
      const pr = el("span", "pr");
      if (n.status === "sold") {
        pr.textContent = `${fmt(n.sold_price)}  (-${S.me.items[it.id].bought ? S.me.items[it.id].bought.discount_pct : 0}%)`;
      } else if (n.ask < it.list) {
        pr.append(el("s", "", fmt(it.list)), document.createTextNode(fmt(n.ask)));
      } else if (n.ask > it.list) {
        pr.classList.add("up");
        pr.append(el("s", "", fmt(it.list)), document.createTextNode("↑ " + fmt(n.ask)));
      } else {
        pr.textContent = "Sticker " + fmt(it.list);
      }
      b.append(pr, el("span", "st", n.status === "sold" ? "Bagged!" : n.status === "final" ? "Final price" : n.chat.length ? "Haggling…" : "Tap to haggle"));
      b.onclick = () => openSheet(it.id);
      box.append(b);
    }
    const bought = Object.values(S.me.items).filter((x) => x.status === "sold").length;
    $("#bagN").textContent = `${bought}/${N()}`;
    $("#spent").textContent = fmt(S.me.spent);
    $("#saved").textContent = bought ? `${S.me.saved_pct}%` : "–";
  }

  function renderBoard(ol, rows) {
    ol.textContent = "";
    const myId = S.me && S.me.id;
    let inList = false;
    for (const r of rows) {
      const li = el("li", r.id === myId ? "me" : "");
      if (r.id === myId) inList = true;
      li.append(el("span", "nm", r.name + (r.completed ? " ✅" : "")), el("span", "sp", `${r.n}/${N()} · ${fmt(r.spent)}`));
      ol.append(li);
    }
    if (!inList && S.me && S.state && S.state.ranks[myId]) {
      const li = el("li", "me");
      li.dataset.rk = S.state.ranks[myId];
      li.append(el("span", "nm", "You: " + S.me.name), el("span", "sp", `${Object.values(S.me.items).filter((x) => x.status === "sold").length}/${N()} · ${fmt(S.me.spent)}`));
      ol.append(li);
    }
    if (!rows.length) ol.append(el("li", "muted", "Nobody yet"));
  }

  function renderLive() {
    const s = S.state;
    if (!s) return;
    if (S.me) $("#lobbyN").textContent = s.n_players;
    const d = $("#miniDeals");
    d.textContent = "";
    if (!s.deals.length) d.append(el("li", "muted", "No deals yet. Be the first!"));
    for (const x of s.deals.slice(0, 5)) {
      const li = el("li");
      li.append(el("span", "emoji", x.emoji), el("span", "nm", `${x.player} bagged ${x.item_name}`), el("span", "pct", `-${x.discount_pct}%`));
      d.append(li);
    }
    renderBoard($("#miniBoard"), s.top.slice(0, 5));
  }

  // ---------------------------------------------------------------- haggle sheet
  function openSheet(id) {
    if (!S.state || S.state.status !== "live") { toast(`${S.game.shopkeeper} hasn't opened the shop yet.`); return; }
    S.cur = id;
    const it = itemOf(id);
    $("#shEmoji").textContent = it.emoji;
    $("#shName").textContent = it.name;
    $("#shList").textContent = " · sticker " + fmt(it.list);
    Anna.mood($("#shAv"), "neutral");
    renderChat();
    renderSheet();
    $("#sheet").classList.remove("hidden");
    document.body.classList.add("noscroll");
    if (S.me.items[id].status !== "sold") setTimeout(() => $("#msg").focus(), 60);
  }

  function closeSheet() {
    S.cur = null;
    $("#sheet").classList.add("hidden");
    document.body.classList.remove("noscroll");
  }

  function addBubble(kind, text, typed, tag) {
    const box = $("#chat");
    const m = el("div", "msg " + (kind === "me" ? "me" : kind === "sys" ? "sys" : kind === "typing" ? "bj typing" : "bj"));
    let body = m;
    if (kind === "bj") { m.append(el("span", "who", S.game.shopkeeper)); body = el("span"); m.append(body); }
    box.append(m);
    if (tag) m.append(el("span", tag.startsWith("↑") ? "pricetag up" : tag.startsWith("Agreed") ? "pricetag agree" : "pricetag", tag));
    if (typed) {
      const total = text.length, step = Math.max(1, Math.ceil(total / 50));
      let i = 0;
      const t = setInterval(() => {
        i = Math.min(total, i + step);
        body.textContent = text.slice(0, i);
        box.scrollTop = box.scrollHeight;
        if (i >= total) clearInterval(t);
      }, 24);
    } else {
      body.textContent = text;
    }
    box.scrollTop = box.scrollHeight;
    return m;
  }

  // The price shown next to each of Anna's lines comes from the game engine, never from the AI's words.
  function priceTag(kind, ask) {
    if (!ask) return "";
    if (kind === "DEAL") return `SOLD at ${fmt(ask)}`;
    if (kind === "RAISE") return `↑ He raised it: ${fmt(ask)}`;
    if (kind === "CONFIRM") return `Agreed at ${fmt(ask)} · tap Buy to take it`;
    if (["COUNTER", "HOLD", "FINAL", "WALK_CALLBACK"].includes(kind)) return `His price: ${fmt(ask)}`;
    return "";
  }

  // "12% off sticker", or "5% above sticker" once his temper has pushed the price over it
  function offLabel(ask, list) {
    const p = Math.round(100 * (1 - ask / list));
    return p > 0 ? `${p}% off sticker` : p < 0 ? `${-p}% above sticker` : "the sticker price";
  }

  const VIBES = { angry: "😠 Angry", cold: "😒 Cold", neutral: "😐 Neutral", warm: "🙂 Warm", friendly: "😄 Friendly" };

  function renderChat() {
    $("#chat").textContent = "";
    const n = S.me.items[S.cur], it = itemOf(S.cur);
    if (!n.chat.length) {
      addBubble("bj", `Arre, ${S.me.name}! ${it.name}? Excellent choice. Price is ${fmt(it.list)}. Fixed price, no bargaining in my shop!* Go on, tell me what you want to pay.`, false);
    }
    for (const m of n.chat) addBubble(m.role === "me" ? "me" : "bj", m.text, false, m.role === "me" ? "" : priceTag(m.kind, m.ask));
    if (n.status === "sold") addBubble("sys", `Sold! You bagged it for ${fmt(n.sold_price)}.`, false);
  }

  function renderSheet() {
    if (!S.cur || !S.me) return;
    const n = S.me.items[S.cur], it = itemOf(S.cur);
    const live = S.state && S.state.status === "live";
    const sold = n.status === "sold";
    $("#shAsk").textContent = fmt(sold ? n.sold_price : n.ask);
    $("#shAsk").classList.toggle("up", !sold && n.ask > it.list);
    const p = $("#patience");
    p.textContent = "";
    for (let i = 0; i < (n.patience_max || S.game.patience); i++) p.append(el("i", i < n.patience ? "" : "off"));
    p.classList.toggle("low", n.patience <= 1 && !sold);
    const v = $("#vibe"), vb = sold ? "friendly" : (n.vibe || "neutral");
    v.className = "vibe " + vb;
    v.textContent = sold ? "😄 Deal done" : VIBES[vb] || VIBES.neutral;
    $("#finalTag").classList.toggle("hidden", !(n.status === "final" && !sold));
    const buy = $("#btnBuy");
    buy.textContent = sold ? "✓ Bagged" : n.ask > S.me.wallet ? `Can't afford ${fmt(n.ask)}` : `Buy at ${fmt(n.ask)}`;
    buy.disabled = sold || !live || S.sending || n.ask > S.me.wallet;
    buy.classList.toggle("glow", !sold && n.ask <= S.me.wallet && (n.status === "final" || !!n.agreed || S.glow === S.cur));
    const walk = $("#btnWalk");
    walk.disabled = sold || !live || S.sending || n.walk_used;
    walk.textContent = n.walk_used ? "🚶 Already tried" : "🚶 Walk away";
    $("#msg").disabled = sold || !live || S.sending;
    $("#btnSend").disabled = sold || !live || S.sending;
    $("#msg").placeholder = sold ? "Deal done. Pick another item." : "Make your offer… e.g. I'll pay " + Math.round(it.list * 0.75 / 10) * 10;
  }

  async function act(path, body, mineText) {
    if (S.sending || !S.cur) return;
    const id = S.cur;
    S.sending = true;
    S.glow = null;
    renderSheet();
    const mine = mineText ? addBubble("me", mineText, false) : null;
    const typing = addBubble("typing", "• • •", false);
    const r = await api(path, { item_id: id, ...body });
    typing.remove();
    S.sending = false;
    if (!r.ok) {
      if (mine) mine.remove();
      if (body.message != null) $("#msg").value = body.message;
      toast(r.error || "Try again.");
      if (r.code === "not_live" || r.code === "sold") await refreshMe().then(route);
      renderSheet();
      return;
    }
    applyResult(r, id);
  }

  function applyResult(r, id) {
    S.me = r.me;
    if (r.kind === "CONFIRM") S.glow = id;
    sfx.reply(r);
    if (S.cur === id) {
      Anna.mood($("#shAv"), r.mood);
      addBubble("bj", r.reply, true, priceTag(r.kind, r.deal ? r.deal.price : r.neg.ask));
      if (r.kind === "CONFIRM") addBubble("sys", `He agrees to ${fmt(r.neg.ask)}. Nothing is sold until you tap Buy.`, false);
    }
    if (r.deal) celebrate(r.deal);
    renderTop();
    renderShelf();
    if (S.cur === id) renderSheet();
    if (r.kind === "RAISE" && S.cur === id) {
      const a = $("#shAsk");
      a.classList.remove("bump");
      void a.offsetWidth;
      a.classList.add("bump");
    }
  }

  const ACCEPT_ONLY = /^\s*((ok(ay)?|okey|deal|done|yes|yep|fine|agreed|sold|chalo|theek hai|thik hai|ha+n?|take it|i('ll| will)? take it|thanks|thank you)[\s,.!]*){1,3}$/i;

  function send() {
    const input = $("#msg");
    const text = input.value.trim();
    if (!text) return;
    if (ACCEPT_ONLY.test(text)) { input.value = ""; confirmBuy(); return; }   // saying "deal" never buys by itself
    input.value = "";
    act("/api/haggle", { message: text }, text);
  }

  // ---------------------------------------------------------------- buying (always an explicit, confirmed tap)
  function showOverlay(build) {
    const ov = $("#overlay"), card = ov.querySelector(".overlay-card");
    card.textContent = "";
    build(card, () => ov.classList.add("hidden"));
    ov.classList.remove("hidden");
  }

  function confirmBuy() {
    const id = S.cur;
    if (!id || S.sending) return;
    const n = S.me.items[id], it = itemOf(id);
    if (n.status === "sold" || n.ask > S.me.wallet) return;
    const after = S.me.wallet - n.ask;
    const others = Object.values(S.me.items).filter((x) => x.status !== "sold").length - 1;
    const leftAfter = S.me.left_sticker - it.list;
    const need = leftAfter > 0 ? Math.max(0, Math.round(100 * (1 - after / leftAfter))) : 0;
    showOverlay((card, close) => {
      card.append(el("h2", "", `Buy the ${it.name}?`), el("p", "big", `${fmt(n.ask)}  (${offLabel(n.ask, it.list)})`));
      if (others > 0) {
        const line = el("p", need >= 15 ? "warnline" : "muted",
          `You'd have ${fmt(after)} left for the other ${others} item${others > 1 ? "s" : ""} (sticker ${fmt(leftAfter)}). ` +
          (need >= 15 ? `You would need about ${need}% off on all of them, and that is very hard.` : need > 0 ? `You'd need about ${need}% off on them.` : "You can afford them all."));
        card.append(line);
      }
      const row = el("div", "overlay-row");
      const yes = el("button", "btn teal", "Yes, buy it"), no = el("button", "btn ghost", "Keep haggling");
      yes.onclick = () => { close(); act("/api/buy", {}, null); };
      no.onclick = close;
      row.append(no, yes);
      card.append(row);
    });
  }

  // ---------------------------------------------------------------- celebrations
  function toast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    t.classList.remove("hidden");
    clearTimeout(toast.t);
    toast.t = setTimeout(() => t.classList.add("hidden"), 2800);
  }

  function confetti(n = 26) {
    const em = ["🎉", "🪙", "✨", "💰", "🛍️"];
    for (let i = 0; i < n; i++) {
      const s = el("span", "fly", em[i % em.length]);
      s.style.left = 30 + Math.random() * 40 + "vw";
      s.style.top = "62vh";
      s.style.fontSize = 18 + Math.random() * 18 + "px";
      document.body.append(s);
      const dx = (Math.random() - 0.5) * 380, dy = -(140 + Math.random() * 280);
      s.animate([{ transform: "translate(0,0) rotate(0)", opacity: 1 },
                 { transform: `translate(${dx}px,${dy}px) rotate(${(Math.random() - 0.5) * 540}deg)`, opacity: 0 }],
                { duration: 1100 + Math.random() * 700, easing: "cubic-bezier(.2,.8,.3,1)" }).onfinish = () => s.remove();
    }
  }

  function celebrate(d) {
    confetti();
    toast(`${d.emoji} Bagged ${d.item_name} for ${fmt(d.price)} (${d.discount_pct}% off)!`);
    if (Object.values(S.me.items).every((x) => x.status === "sold")) setTimeout(basketComplete, 1100);
  }

  function basketComplete() {
    sfx.play("fanfare");
    const ov = $("#overlay"), card = ov.querySelector(".overlay-card");
    card.textContent = "";
    card.append(el("h2", "", "🎉 Basket complete!"),
                el("p", "big", `Your total: ${fmt(S.me.spent)}`),
                el("p", "muted", `${S.me.saved_pct}% below sticker. Others are still shopping, so watch the leaderboard!`));
    const b = el("button", "btn", "Back to the bazaar");
    b.onclick = () => ov.classList.add("hidden");
    card.append(b);
    ov.classList.remove("hidden");
    closeSheet();
    confetti(40);
  }

  // ---------------------------------------------------------------- results
  function renderEnd() {
    const s = S.state, me = S.me;
    if (me) {
      const rk = s.ranks[me.id] || "–";
      const bought = Object.values(me.items).filter((x) => x.status === "sold").length;
      $("#endLine").textContent = me.completed
        ? `You finished #${rk} of ${s.n_players}, with a total of ${fmt(me.spent)}`
        : `You bagged ${bought}/${N()} items and ranked #${rk} of ${s.n_players}`;
      $("#endSub").textContent = me.completed
        ? `That is ${me.saved_pct}% below the sticker prices.`
        : "Baskets that were filled completely rank ahead of the rest.";
    } else {
      $("#endLine").textContent = "You just missed it!";
      $("#endSub").textContent = "Here is how it went. Thanks for playing!";
    }
    const box = $("#endAwards");
    box.textContent = "";
    for (const a of s.awards || []) {
      const c = el("div", "award");
      c.append(el("span", "em", a.emoji), el("b", "", a.title), el("span", "who", a.name), el("span", "muted", a.detail));
      box.append(c);
    }
    renderBoard($("#endBoard"), s.top);
  }

  // ---------------------------------------------------------------- wiring
  $("#btnJoin").onclick = join;
  $("#name").addEventListener("keydown", (e) => { if (e.key === "Enter") join(); });
  $("#btnBack").onclick = closeSheet;
  $("#chatForm").addEventListener("submit", (e) => { e.preventDefault(); send(); });
  $("#btnBuy").onclick = confirmBuy;
  $("#btnWalk").onclick = () => act("/api/walk", {}, "🚶 (picks up the bag and walks away…)");
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && S.cur) closeSheet(); });

  boot();
})();
