"""Data model, ranking and awards. Plain dataclasses; JSON-serialisable."""
from __future__ import annotations

import asyncio
import copy
import re
import unicodedata
from dataclasses import asdict, dataclass, field, fields

from .referee import Neg
from .safety import is_profane_name

MIN_NAME = 4
MAX_NAME = 18
_NEG_FIELDS = {f.name for f in fields(Neg)}      # a saved game from an older version may carry fields that no longer exist


class BadName(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _name_chars(s: str) -> str:
    """Keep letters, combining marks and digits of any script, spaces, . ' - and emoji. Drop everything else."""
    out: list[str] = []
    for ch in s:
        cat = unicodedata.category(ch)
        o = ord(ch)
        if cat[0] in "LMN" or ch in " .'-" or 0x1F300 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF:
            out.append(ch)
        elif ch in "\u200c\u200d" and out and 0x0900 <= ord(out[-1]) <= 0x0DFF:
            out.append(ch)          # ZWJ/ZWNJ shape Indian-script words
    return "".join(out)


def clean_name(raw: str, taken: set[str]) -> str:
    """A safe, readable display name. Raises BadName if it is too short or not allowed (the shopper picks another)."""
    s = unicodedata.normalize("NFKC", raw or "")
    s = re.sub(r"\s+", " ", _name_chars(s)).strip()[:MAX_NAME]
    core = sum(1 for ch in s if unicodedata.category(ch)[0] in "LMN")
    letters = sum(1 for ch in s if unicodedata.category(ch)[0] == "L")
    if core < MIN_NAME or letters < 2 or len(set(s.lower().replace(" ", ""))) < 2:
        raise BadName("name_short", f"Please use at least {MIN_NAME} characters for your name.")
    if is_profane_name(s):
        raise BadName("name_bad", "Please pick a different name.")
    base, n = s, 2
    low = {t.lower() for t in taken}
    while s.lower() in low:
        s = f"{base[:15]} {n}"
        n += 1
    return s


@dataclass
class Player:
    id: str
    token: str
    name: str
    joined_at: float
    wallet: int
    spent: int = 0
    negs: dict[str, Neg] = field(default_factory=dict)
    bought: dict[str, dict] = field(default_factory=dict)     # item_id -> {price, at, discount_pct}
    chat: dict[str, list] = field(default_factory=dict)       # item_id -> [{role, text, kind}]
    completed_at: float = 0.0
    tricks: int = 0
    wits: int = 0
    msgs: int = 0
    last_action: float = 0.0
    last_msg: str = ""
    window: list = field(default_factory=list)                 # recent action timestamps (rate limit)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False, compare=False)

    def to_dict(self) -> dict:
        out = {}
        for f in fields(self):
            if f.name in ("lock", "window"):
                continue
            v = getattr(self, f.name)
            out[f.name] = {k: asdict(n) for k, n in v.items()} if f.name == "negs" else copy.deepcopy(v)
        return out

    @classmethod
    def from_dict(cls, d: dict) -> "Player":
        d = dict(d)
        d["negs"] = {k: Neg(**{f: x for f, x in v.items() if f in _NEG_FIELDS}) for k, v in d.get("negs", {}).items()}
        return cls(**d)


def rank_key(p: Player, n_items: int):
    done = len(p.bought) == n_items
    sticker = sum(b["list"] for b in p.bought.values()) or 1
    if done:
        return (0, p.spent, p.completed_at)
    return (1, -len(p.bought), p.spent / sticker, p.joined_at)


def leaderboard(players: dict[str, Player], n_items: int, list_total: int) -> list[dict]:
    order = sorted(players.values(), key=lambda p: rank_key(p, n_items))
    rows = []
    for i, p in enumerate(order, 1):
        sticker = sum(b["list"] for b in p.bought.values())
        done = len(p.bought) == n_items
        rows.append({
            "id": p.id, "name": p.name, "rank": i, "bought": list(p.bought.keys()), "n": len(p.bought),
            "spent": p.spent, "saved_pct": round(100 * (1 - p.spent / sticker)) if sticker else 0,
            "completed": done, "completed_at": p.completed_at,
            "broke": (not done) and p.wallet < 150,
        })
    return rows


def awards(players: dict[str, Player], deals: list[dict], n_items: int, started_at: float, reveal: bool = True,
           keeper: str = "Anna") -> list[dict]:
    out = []
    rows = leaderboard(players, n_items, 0)
    if rows and rows[0]["completed"]:
        w = rows[0]
        out.append({"id": "winner", "emoji": "🏆", "title": "Mol-Bhav Maestro", "name": w["name"],
                    "detail": f"Bought everything for ₹{w['spent']:,} ({w['saved_pct']}% off)"})
    if deals:
        b = max(deals, key=lambda d: (d["discount_pct"], -d["at"]))
        what = f"for ₹{b['price']:,} " if reveal else ""
        out.append({"id": "bigdeal", "emoji": "💥", "title": "Biggest Single Discount", "name": b["player"],
                    "detail": f"{b['item_name']} {what}({b['discount_pct']}% off)"})
    done = [p for p in players.values() if len(p.bought) == n_items and p.completed_at]
    if done and started_at:
        f = min(done, key=lambda p: p.completed_at)
        secs = max(1, int(f.completed_at - started_at))
        out.append({"id": "fast", "emoji": "⚡", "title": "Speed Shopper", "name": f.name,
                    "detail": f"Finished the whole list in {secs // 60}m {secs % 60:02d}s"})
    t = max(players.values(), key=lambda p: p.tricks, default=None)
    if t and t.tricks > 0:
        out.append({"id": "trickster", "emoji": "🕵️", "title": "Chief Trickster", "name": t.name,
                    "detail": f"Tried {t.tricks} sneaky trick{'s' if t.tricks != 1 else ''}. {keeper} was unmoved."})
    w = max(players.values(), key=lambda p: p.wits, default=None)
    if w and w.wits > 0:
        out.append({"id": "wit", "emoji": "😂", "title": f"Made {keeper} Laugh", "name": w.name,
                    "detail": f"Charmed {keeper} {w.wits} time{'s' if w.wits != 1 else ''}"})
    hikes = {p.id: sum(n.bumps for n in p.negs.values()) for p in players.values()}
    if hikes and max(hikes.values()) > 0:
        r = players[max(hikes, key=hikes.get)]
        out.append({"id": "pricehike", "emoji": "😤", "title": f"Pushed {keeper}'s Buttons", "name": r.name,
                    "detail": f"Made {keeper} put the price up {hikes[r.id]} time{'s' if hikes[r.id] != 1 else ''}"})
    return out
