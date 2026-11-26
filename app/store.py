"""Game store: the authoritative state. Prices are decided by app.referee; money moves only here."""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import secrets
import time
from collections import deque
from pathlib import Path

from . import referee
from .config import Game, Settings
from .lang import detect_script
from .lines import fallback_line, money
from .models import BadName, Player, awards, clean_name, leaderboard
from .referee import TEMPERS, clean_text, new_neg, parse_message, tag_numbers
from .voice import PRICE, Reply, Turn, Voice


class Err(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class Bus:
    def __init__(self):
        self.subs: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=300)
        self.subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subs.discard(q)

    def publish(self, ev: dict) -> None:
        for q in list(self.subs):
            try:
                q.put_nowait(ev)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                    q.put_nowait(ev)
                except Exception:  # noqa: BLE001
                    pass


def mood_for(kind: str, base: str, discount_pct: int) -> str:
    if kind == "DEAL":
        return "sobbing" if discount_pct >= 22 else "pleased"
    return base


_PRICE = re.compile(r"₹\s?\d[\d,]*")
_PUBLIC_FX = {"join", "leave", "deal", "complete", "status", "reset", "event"}
_PRICE_DECISIONS = ("COUNTER", "HOLD", "RAISE", "FINAL", "WALK_CALLBACK", "CONFIRM", "DEAL")
# Which of the AI's pre-written lines goes with which move the referee decided. A sale has no pre-written line on purpose: it only
# ever comes from the Buy button, and that line is the register's own.
_LINE_FOR = {"COUNTER": "concede", "HOLD": "hold", "RAISE": "raise", "CONFIRM": "agree"}

# Market events: short, announced mood swings of the whole shop. They scale every concession for everyone at once.
EVENTS = {
    "rush": {"mult": 1.30, "title": "FESTIVE RUSH!", "emoji": "🔥",
             "text": "The shop is packed and {keeper} is flustered. He gives ground more easily right now!"},
    "tight": {"mult": 0.75, "title": "MONTH-END SQUEEZE", "emoji": "😤",
              "text": "Cash is tight and {keeper} is extra stubborn right now. Concessions are harder to win."},
}
EVENT_SECONDS = 45


class Store:
    def __init__(self, game: Game, settings: Settings, voice: Voice, clock=time.time, transcript: bool = True,
                 rng: random.Random | None = None, auto_events: bool = True):
        self.g, self.s, self.voice, self.now = game, settings, voice, clock
        self.rng = rng or random.Random(secrets.randbits(64))
        self.auto_events = auto_events
        self.bus = Bus()      # players: trimmed snapshots + a few public events
        self.abus = Bus()     # admin screen: everything
        self.transcript = transcript
        self._last_public = 0.0
        self.reset(save=False)

    # ------------------------------------------------------------------ lifecycle
    def reset(self, save: bool = True) -> None:
        self.status = "lobby"           # lobby | live | ended
        self.players: dict[str, Player] = {}
        self.tokens: dict[str, str] = {}
        self.started_at = self.ends_at = self.ended_at = 0.0
        self.duration = self.g.duration_min * 60
        self.deals: deque[dict] = deque(maxlen=80)
        self.deal_log: list[dict] = []     # every deal, for awards and export (deals above is just the ticker)
        self.lines: deque[dict] = deque(maxlen=30)
        self.tricks_total = 0
        self.discount_total = 0
        self.mood = "neutral"
        self.reveal = False             # show exact prices on shared screens?
        self.market: dict | None = None  # the running market event, if any
        self.event_plan: list[tuple[float, str]] = []
        self.version = 0
        self.dirty = False
        if save:
            self.fx({"type": "reset"})
            self.touch()

    def touch(self) -> None:
        self.version += 1
        self.dirty = True

    def set_reveal(self, on: bool) -> None:
        self.reveal = bool(on)
        self.touch()

    def mask(self, text: str) -> str:
        return text if self.reveal else _PRICE.sub("₹•••", text)

    def deal_view(self, d: dict) -> dict:
        v = {k: d[k] for k in ("player", "pid", "item_id", "item_name", "emoji", "discount_pct", "at")}
        if self.reveal:
            v["price"], v["list"] = d["price"], d["list"]
        return v

    def fx(self, ev: dict) -> None:
        ev["t"] = self.now()
        if ev.get("type") in ("deal", "line"):
            ev = {**ev}
            if ev["type"] == "deal":
                ev = {**self.deal_view(ev), "type": "deal", "t": ev["t"]}
            else:
                ev["text"] = self.mask(ev.get("text", ""))
        self.abus.publish({"event": "fx", "data": ev})
        if ev.get("type") in _PUBLIC_FX:
            self.bus.publish({"event": "fx", "data": ev})

    def start(self, minutes: int | None = None) -> None:
        if self.status == "live":
            return
        if self.status == "ended":
            raise Err("ended", "The bazaar is closed. Use New game first.", 409)
        if minutes is not None:
            self.duration = max(0, int(minutes)) * 60
        self.status, self.started_at = "live", self.now()
        self.ends_at = self.started_at + self.duration if self.duration else 0.0
        self.event_plan = self._plan_events() if self.auto_events else []
        self.fx({"type": "status", "status": "live"})
        self.touch()

    def extend(self, seconds: int = 120) -> None:
        if self.status == "live":
            self.ends_at = (self.ends_at or self.now()) + int(seconds)
            self.touch()

    def end(self) -> None:
        if self.status != "live":
            return
        self.status, self.ended_at = "ended", self.now()
        self.market = None
        self.fx({"type": "status", "status": "ended"})
        self.touch()

    def kick(self, pid: str) -> None:
        p = self.players.pop(pid, None)
        if p:
            self.tokens.pop(p.token, None)
            self.fx({"type": "leave", "name": p.name})
            self.touch()

    # ------------------------------------------------------------------ market events
    def _plan_events(self) -> list[tuple[float, str]]:
        """A few events at random moments of a long enough game, never two of the same kind in a row."""
        if not self.duration or self.duration < 360:
            return []
        n = 3 if self.duration >= 600 else 2
        plan, last = [], ""
        for i in range(n):
            lo, hi = (i + 0.7) / (n + 0.6), (i + 1.3) / (n + 0.6)
            kind = self.rng.choice([k for k in EVENTS if k != last])
            plan.append((self.rng.uniform(lo, hi) * self.duration, kind))
            last = kind
        return plan

    def start_event(self, kind: str, seconds: int = EVENT_SECONDS) -> None:
        ev = EVENTS.get(kind)
        if self.status != "live" or not ev:
            return
        self.market = {"kind": kind, "mult": ev["mult"], "title": ev["title"], "emoji": ev["emoji"],
                       "text": ev["text"].format(keeper=self.g.shopkeeper), "until": self.now() + seconds}
        self.fx({"type": "event", "kind": kind, "title": ev["title"], "emoji": ev["emoji"], "text": self.market["text"],
                 "until": self.market["until"]})
        self.touch()

    def clear_event(self) -> None:
        if self.market:
            self.market = None
            self.fx({"type": "event", "kind": "", "title": "", "emoji": "", "text": "", "until": 0})
            self.touch()

    def market_mult(self) -> float:
        return self.market["mult"] if self.market and self.now() < self.market["until"] else 1.0

    def market_view(self) -> dict | None:
        m = self.market
        if not m or self.now() >= m["until"]:
            return None
        return {k: m[k] for k in ("kind", "title", "emoji", "text", "until")}

    def tick(self) -> None:
        """Called every second by the server (and directly by tests): ends the game on time, runs market events,
        pushes fresh snapshots."""
        t = self.now()
        if self.status == "live" and self.ends_at and t >= self.ends_at:
            self.end()
        if self.status == "live":
            if self.market and t >= self.market["until"]:
                self.clear_event()
            if not self.market and self.event_plan and t - self.started_at >= self.event_plan[0][0]:
                _, kind = self.event_plan.pop(0)
                self.start_event(kind)
        if self.dirty or t - self._last_public >= 5:
            if self.abus.subs:
                self.abus.publish({"event": "snapshot", "data": self.snapshot()})
            if self.bus.subs and (t - self._last_public >= 1.5 or self.status == "ended"):
                self.bus.publish({"event": "snapshot", "data": self.public_snapshot()})
                self._last_public = t
            if self.dirty:
                self.dirty = False
                self._save()

    async def run_clock(self) -> None:
        while True:
            await asyncio.sleep(1.0)
            try:
                self.tick()
            except Exception:  # noqa: BLE001  (never let a bug in a snapshot kill the clock)
                pass

    # ------------------------------------------------------------------ players
    def join(self, name: str) -> Player:
        """Anyone can join at any time before the shop closes, including while the game is already running."""
        if self.status == "ended":
            raise Err("ended", "The bazaar has closed. See you next time!", 409)
        if len(self.players) >= self.g.max_players:
            raise Err("full", "The bazaar is full.", 429)
        try:
            name = clean_name(name, {p.name for p in self.players.values()})
        except BadName as e:
            raise Err(e.code, e.message, 400)
        p = Player(id=secrets.token_hex(4), token=secrets.token_urlsafe(24), name=name, joined_at=self.now(), wallet=self.g.budget)
        p.negs = {i.id: new_neg(i, self.g.diff, self.rng) for i in self.g.items}
        self.players[p.id] = p
        self.tokens[p.token] = p.id
        self.fx({"type": "join", "name": p.name})
        self.touch()
        return p

    def auth(self, token: str) -> Player:
        pid = self.tokens.get(token or "")
        p = self.players.get(pid or "")
        if not p:
            raise Err("auth", "Please rejoin the bazaar.", 401)
        return p

    # ------------------------------------------------------------------ actions
    def _check(self, p: Player, item_id: str):
        if self.status != "live":
            raise Err("not_live", "The shop is closed right now." if self.status == "ended"
                      else f"{self.g.shopkeeper} hasn't opened the shop yet.", 409)
        it = self.g.item(item_id)
        if not it:
            raise Err("item", "No such item.", 404)
        if p.negs[it.id].status == "sold":
            raise Err("sold", "You already bought that one.", 409)
        t = self.now()
        p.window = [x for x in p.window if t - x < 60]
        if t - p.last_action < 0.8 or len(p.window) >= 45 or p.msgs >= 600:
            raise Err("slow", "Easy, boss! One thing at a time.", 429)
        p.last_action = t
        p.window.append(t)
        return it

    def _commit_sale(self, p: Player, it, price: int) -> dict:
        neg = p.negs[it.id]
        neg.status, neg.sold_price, neg.ask = "sold", price, price
        p.wallet -= price
        p.spent += price
        disc = max(0, round(100 * (1 - price / it.list)))      # paying above the sticker (after annoying him) is a 0% deal, not a negative one
        p.bought[it.id] = {"price": price, "list": it.list, "at": self.now(), "discount_pct": disc}
        deal = {"player": p.name, "pid": p.id, "item_id": it.id, "item_name": it.name, "emoji": it.emoji, "price": price,
                "list": it.list, "discount_pct": disc, "at": self.now()}
        self.deals.appendleft(deal)
        self.deal_log.append(deal)
        self.discount_total += it.list - price
        self.fx({"type": "deal", **deal})
        if len(p.bought) == len(self.g.items):
            p.completed_at = self.now()
            self.fx({"type": "complete", "name": p.name, "spent": p.spent})
        return deal

    def _say(self, p: Player, it, kind: str, text: str, mood: str) -> None:
        self.lines.appendleft({"player": p.name, "item": it.name, "emoji": it.emoji, "text": text, "kind": kind,
                               "mood": mood, "at": self.now()})
        self.mood = mood
        self.fx({"type": "line", "player": p.name, "item": it.name, "emoji": it.emoji, "text": text, "kind": kind, "mood": mood})

    def _log(self, **ev) -> None:
        if not self.transcript:
            return
        try:
            self.s.data_dir.mkdir(parents=True, exist_ok=True)
            with open(self.s.data_dir / "events.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": round(self.now(), 1), **ev}, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _remember(self, p: Player, it, mine: str, text: str, kind: str, ask: int) -> None:
        log = p.chat.setdefault(it.id, [])
        if mine:
            log.append({"role": "me", "text": mine})
        log.append({"role": "keeper", "text": text, "kind": kind, "ask": ask})
        del log[:-40]

    def _turn(self, p: Player, it, text: str, parsed, kind: str, *, ratio: float = 0.0, mood: str = "thinking", price=None,
              negotiate: bool = False) -> Turn:
        neg = p.negs[it.id]
        hist = [("customer" if m["role"] == "me" else "you", m["text"]) for m in p.chat.get(it.id, [])[-4:]]
        flags = ["the customer used a rude word"] if parsed.rude else []
        t = Turn(key=p.id, item_name=it.name, kind=kind, message=text, mood=mood, feeling=referee.vibe(neg),
                 temper=TEMPERS[neg.temper][4], patience=neg.patience, patience_max=neg.patience0, loyalty=len(p.bought),
                 ratio=ratio, script=detect_script(text), history=hist,
                 big_discount=bool(price and round(100 * (1 - price / it.list)) >= 22), flags=tuple(flags))
        if negotiate:
            vals = [v for _, _, v in parsed.spans]
            t.tagged, t.numbers, t.num_ratios = tag_numbers(text, parsed.spans), vals, [v / neg.ask for v in vals]
        return t

    async def _respond(self, p: Player, it, text: str, parsed, *, plan=None, dec=None, speak: bool = True,
                       buying: bool = False) -> dict:
        """A turn the register can settle without weighing the shopper's reasons (and the Buy button and the walk-away). The
        decision is applied first, so state never lags the AI call; the AI only supplies the voice. `buying` is True only for
        the Buy button: it is the one and only caller that may complete a sale."""
        d, neg = self.g.diff, p.negs[it.id]
        if plan is not None:
            dec = referee.commit(it, neg, plan, d, p.wallet, parsed.rude, self.rng)
        if dec.kind == "DEAL" and not buying:          # defence in depth: nothing a shopper types can ever sell anything
            dec = referee.Decision("CONFIRM", neg.ask, neg.patience, referee.MOOD["CONFIRM"], price=neg.ask)
        deal = self._commit_sale(p, it, dec.price) if dec.kind == "DEAL" else None
        turn = self._turn(p, it, text, parsed, dec.kind, ratio=(plan.ratio if plan is not None else 0.0), mood=dec.mood,
                          price=dec.price if dec.kind == "DEAL" else None)
        reply = await self.voice.respond(turn) if speak else Reply(None, "fallback")
        return self._finish(p, it, text, dec, deal, turn, reply.text, reply.source, reply.wit, reply.ms, reply.why)

    async def _negotiate(self, p: Player, it, text: str, parsed, plan) -> dict:
        """A serious offer. The AI reads the message (and pre-writes its lines) before anything changes; then the referee weighs
        that read against the offer, the shopper's manners and his own mood, and decides what he does."""
        d, neg = self.g.diff, p.negs[it.id]
        ambiguous = plan.kind == "AMBIGUOUS"
        turn = self._turn(p, it, text, parsed, "NEGOTIATE", ratio=0.0 if ambiguous else plan.ratio, negotiate=True)
        perc = await self.voice.perceive(turn)
        if self.status != "live":
            raise Err("not_live", "The shop just closed.", 409)       # nothing was changed
        if ambiguous:
            # Several numbers in one message: the AI says which is the offer. Without it, he asks which one is meant.
            if perc.offer is None:
                return await self._respond(p, it, text, parsed, plan=plan, speak=False)
            parsed.offer, parsed.intent = perc.offer, "offer"
            plan = referee.plan_message(it, neg, parsed, d, p.wallet)
            if plan.kind != "NEGOTIATE":
                return await self._respond(p, it, text, parsed, plan=plan)
        read = perc.read or referee.lexical_read(text, parsed)
        if read.kind == "trick" and not parsed.trick:
            neg.tricks += 1
            p.tricks += 1
            self.tricks_total += 1
        dec = referee.negotiate(it, neg, plan, read, parsed.rude, d, len(p.bought), p.wallet, self.rng, self.market_mult())
        turn.mood = dec.mood
        return self._finish(p, it, text, dec, None, turn, perc.lines.get(_LINE_FOR.get(dec.kind, "")), perc.source, read.wit,
                            perc.ms, perc.why)

    def _finish(self, p: Player, it, text: str, dec, deal, turn: Turn, line: str | None, source: str, wit: int, ms: int,
                why: str) -> dict:
        """Put the decision into words (the AI's line when it has one that fits, else a built-in line), record it and reply."""
        neg = p.negs[it.id]
        if dec.kind == "TRICK":
            p.tricks += 1
            self.tricks_total += 1
        disc = deal["discount_pct"] if deal else 0
        price = dec.price if dec.kind in ("DEAL", "CONFIRM") else dec.ask if dec.kind in _PRICE_DECISIONS else None
        if line and (price is not None or PRICE not in line):
            out = line.replace(PRICE, money(price)) if price is not None else line
        else:
            out = fallback_line("RAISE_LOW" if dec.kind == "RAISE" and dec.why == "lowball" else dec.kind, p.id, it.name.lower(), price,
                                disc >= 22, turn.script)
        # A line the AI judged genuinely funny makes Anna laugh on screen (and can earn a fun award), once per item. Cosmetic only.
        laughed = (wit >= 2 and dec.kind in ("COUNTER", "HOLD", "INSULT", "ASK_NUMBER", "CONFIRM") and len(text) >= 12
                   and text.lower() != p.last_msg and not neg.wit_given and neg.status != "sold")
        if laughed:
            neg.wit_given = True
            p.wits += 1
        p.last_msg = text.lower()
        p.msgs += 1
        mood = "pleased" if laughed else mood_for(dec.kind, dec.mood, disc)
        self._remember(p, it, text if text and not text.startswith("(") else "", out, dec.kind, neg.ask)
        self._say(p, it, dec.kind, out, mood)
        self._log(player=p.name, item=it.id, msg=text, kind=dec.kind, ask=neg.ask, floor=neg.floor, temper=neg.temper,
                  reply=out, src=source, ms=ms, wit=wit, why=why, note=dec.note, vibe=referee.vibe(neg))
        self.touch()
        return {"ok": True, "reply": out, "source": source, "mood": mood, "kind": dec.kind, "final": neg.status == "final",
                "deal": deal, "neg": self.neg_view(p, it.id), "me": self.me_view(p)}

    async def haggle(self, token: str, item_id: str, message: str) -> dict:
        p = self.auth(token)
        if p.lock.locked():
            raise Err("busy", f"{self.g.shopkeeper} is still answering. One moment!", 429)
        async with p.lock:
            it = self._check(p, item_id)
            text = clean_text(message)
            if not text:
                raise Err("empty", "Say something, boss!", 400)
            parsed = parse_message(text)
            if referee.needs_extraction(parsed, text):
                offer, pct = await self.voice.extract_offer(text)      # a price written in words or in an Indian script
                referee.apply_extracted(parsed, offer, pct)
            plan = referee.plan_message(it, p.negs[it.id], parsed, self.g.diff, p.wallet)
            if plan.kind == "NEGOTIATE" or (plan.kind == "AMBIGUOUS" and len(parsed.spans) >= 2 and parsed.pct_off is None):
                return await self._negotiate(p, it, text, parsed, plan)
            return await self._respond(p, it, text, parsed, plan=plan)

    async def walk(self, token: str, item_id: str) -> dict:
        p = self.auth(token)
        if p.lock.locked():
            raise Err("busy", f"{self.g.shopkeeper} is still answering. One moment!", 429)
        async with p.lock:
            it = self._check(p, item_id)
            dec = referee.walk_away(it, p.negs[it.id], self.g.diff, self.rng)
            return await self._respond(p, it, "(walks away)", referee.Parsed(), dec=dec)

    async def buy_now(self, token: str, item_id: str) -> dict:
        p = self.auth(token)
        if p.lock.locked():
            raise Err("busy", f"{self.g.shopkeeper} is still answering. One moment!", 429)
        async with p.lock:
            it = self._check(p, item_id)
            dec = referee.buy_at_ask(p.negs[it.id], p.wallet)
            return await self._respond(p, it, "(pays the asking price)", referee.Parsed(), dec=dec, speak=False, buying=True)

    # ------------------------------------------------------------------ views
    def neg_view(self, p: Player, item_id: str) -> dict:
        n = p.negs[item_id]
        return {"item_id": item_id, "status": n.status, "ask": n.ask, "patience": n.patience, "patience_max": n.patience0,
                "rounds": n.rounds, "walk_used": n.walk_used, "sold_price": n.sold_price or None,
                "vibe": referee.vibe(n) if n.status != "sold" else "friendly", "raised": n.bumps,
                "agreed": n.agreed if n.agreed and n.agreed == n.ask and n.status != "sold" else None}

    def me_view(self, p: Player) -> dict:
        rows = leaderboard(self.players, len(self.g.items), 0)
        row = next((r for r in rows if r["id"] == p.id), {})
        left = sum(i.list for i in self.g.items if i.id not in p.bought)
        return {"id": p.id, "name": p.name, "wallet": p.wallet, "spent": p.spent, "rank": row.get("rank"), "of": len(rows),
                "completed": len(p.bought) == len(self.g.items), "saved_pct": row.get("saved_pct", 0),
                "need_to_save": max(0, left - p.wallet), "left_sticker": left,
                "items": {i.id: {**self.neg_view(p, i.id), "bought": p.bought.get(i.id), "chat": p.chat.get(i.id, [])[-30:]}
                          for i in self.g.items}}

    def snapshot(self) -> dict:
        """Full state for the admin screen (the one that is presented, so prices are masked unless revealed)."""
        rows = leaderboard(self.players, len(self.g.items), 0)
        stats = []
        for i in self.g.items:
            sold = [p.bought[i.id]["price"] for p in self.players.values() if i.id in p.bought]
            avg = sum(sold) / len(sold) if sold else 0
            stats.append({"id": i.id, "sold": len(sold), "avg_pct": round(100 * (1 - avg / i.list)) if sold else 0})
        snap = {"status": self.status, "now": self.now(), "started_at": self.started_at, "ends_at": self.ends_at,
                "ended_at": self.ended_at, "duration": self.duration, "version": self.version, "mood": self.mood,
                "reveal": self.reveal, "market": self.market_view(),
                "players": rows,
                "deals": [self.deal_view(d) for d in list(self.deals)[:40]],
                "lines": [{**ln, "text": self.mask(ln["text"])} for ln in list(self.lines)[:14]],
                "stats": {"tricks": self.tricks_total, "discount_total": self.discount_total, "deals": len(self.deal_log),
                          "items": stats, "completed": sum(1 for r in rows if r["completed"])},
                "ai": self.voice.status()}
        if self.status == "ended":
            snap["awards"] = self.public_awards()
        return snap

    def public_awards(self) -> list[dict]:
        return awards(self.players, self.deal_log, len(self.g.items), self.started_at, self.reveal, self.g.shopkeeper)

    def public_snapshot(self) -> dict:
        """Trimmed state for every player's phone: top 10, everyone's rank, recent deals."""
        rows = leaderboard(self.players, len(self.g.items), 0)
        snap = {"status": self.status, "now": self.now(), "ends_at": self.ends_at, "duration": self.duration,
                "n_players": len(rows), "completed": sum(1 for r in rows if r["completed"]), "market": self.market_view(),
                "top": [{k: r[k] for k in ("id", "name", "rank", "n", "spent", "saved_pct", "completed")} for r in rows[:10]],
                "ranks": {r["id"]: r["rank"] for r in rows},
                "deals": [self.deal_view(d) for d in list(self.deals)[:8]]}
        if self.status == "ended":
            snap["awards"] = self.public_awards()
        return snap

    # ------------------------------------------------------------------ persistence
    def _save(self) -> None:
        try:
            self.s.data_dir.mkdir(parents=True, exist_ok=True)
            data = {"status": self.status, "started_at": self.started_at, "ends_at": self.ends_at, "ended_at": self.ended_at,
                    "duration": self.duration, "deal_log": self.deal_log, "lines": list(self.lines), "tricks": self.tricks_total,
                    "discount_total": self.discount_total, "reveal": self.reveal, "event_plan": self.event_plan,
                    "players": [p.to_dict() for p in self.players.values()]}
            tmp = self.s.data_dir / "state.json.tmp"
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.s.data_dir / "state.json")
        except OSError:
            pass

    def load(self) -> bool:
        path: Path = self.s.data_dir / "state.json"
        if not path.exists():
            return False
        d = json.loads(path.read_text(encoding="utf-8"))
        self.reset(save=False)
        self.status, self.started_at, self.ends_at = d["status"], d["started_at"], d["ends_at"]
        self.ended_at, self.duration = d.get("ended_at", 0.0), d["duration"]
        self.deal_log = list(d.get("deal_log", []))
        self.deals = deque(sorted(self.deal_log, key=lambda x: -x["at"])[:80], maxlen=80)
        self.lines.extend(reversed(d.get("lines", [])))
        self.tricks_total, self.discount_total = d.get("tricks", 0), d.get("discount_total", 0)
        self.reveal = bool(d.get("reveal", False))
        self.event_plan = [tuple(x) for x in d.get("event_plan", [])]
        for pd in d["players"]:
            p = Player.from_dict(pd)
            self.players[p.id] = p
            self.tokens[p.token] = p.id
        self.touch()
        return True
