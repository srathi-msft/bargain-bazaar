"""Referee: reads the customer's message and decides what the shop may do. Pure logic, no I/O.

This is the ONLY place that decides money. For every shopper and item it holds hidden numbers (the lowest price he will ever
quote, how quickly he softens, how patient he is) drawn at random when the shopper joins, so nobody gets the same deal and
a trick that works for one person tells another nothing.

How a haggle works (bargaining v2). The AI shopkeeper only READS the shopper: which reason they gave (a rival's price, a flaw,
a bulk promise...), how convincing it was, how warm or hostile they were. That read is a handful of small, validated numbers
(a `Read`); the AI never sees a hidden number, never sets a price and never moves money. This module turns the read into a
move. How far he comes down depends on the offer, on the reason (worth less each time it is repeated, and capped by what a
reason of that kind could ever be worth), on the rapport the shopper has built, and on his mood and luck on the day. Rude,
pushy or lowballing shoppers heat him up: he stops conceding and may even put the price back up a little. He never goes
below his hidden floor, whatever any message or any model says.

The guardrail that matters most: NOTHING a shopper types can ever spend money. When he agrees to a price (an offer he can live
with, or "okay") he only says so (CONFIRM) and holds that price; the sale itself happens in exactly one place, `buy_at_ask`, which
is what the Buy button calls.
"""
from __future__ import annotations

import math
import random
import re
import unicodedata
from dataclasses import dataclass, field, fields

from .lang import NUMBER_WORD_HINT, has_indic
from .safety import is_rude

# ---------------------------------------------------------------- data


@dataclass(frozen=True)
class Item:
    id: str
    name: str
    emoji: str
    list: int          # sticker price = his opening ask
    floor_min: int     # the hidden floor is drawn per shopper between these two numbers
    floor_max: int


@dataclass
class Difficulty:
    patience: int = 5
    max_patience: int = 7
    kappa: float = 0.50           # average share of the gap he concedes per round at full-quality offers
    kappa_spread: float = 0.06    # +/- per shopper and item
    q_insult: float = 0.58        # offer / ask below this is an insult (a lowball): no movement, costs patience, and he shows it
    q_full: float = 0.85          # offers at or above this ratio earn full credit
    q_floor: float = 0.20         # credit at the insult threshold (rises smoothly to 1.0 at q_full)
    q_curve: float = 1.15
    stall_factor: float = 0.40    # an offer that does not beat the previous best moves him much less
    min_step_pct: float = 0.012   # of sticker: a concession smaller than this is not worth announcing, so he holds instead
    loyalty_bonus: float = 0.02   # per item already bought from him (max 5)
    close_tol: float = 0.025      # accepts an offer within this fraction of his ask (if above his floor)
    tired_close_bonus: float = 0.01
    tol_rapport: float = 0.004    # a friendly shopper gets the sale closed a little nearer the ask, per point of rapport
    tol_spread: float = 0.012
    insult_cost: int = 2
    trick_cost: int = 1
    rude_cost: int = 1
    # ---- skill, mood and chaos (bargaining v2)
    s_base: float = 1.0           # how readily he gives ground to a plain, serious offer with no reason behind it
    s_arg: float = 1.50           # extra for the best possible reason (strength 3 of 3), before repeats are discounted
    s_rapport: float = 0.08       # per point of rapport (-3 .. +4)
    s_heat: float = 0.20          # lost per point of heat (0 .. 7)
    s_max: float = 2.2
    noise: float = 0.28           # log-normal spread of his mood on any one reply (his "chaos")
    p_stubborn: float = 0.10      # chance he just does not feel like moving this turn
    p_lucky: float = 0.07         # chance of a generous mood (never when the shopper is hostile)
    repeat_decay: float = 0.5     # a reason used before is worth half as much each time it comes back
    arg_budget: float = 7.0       # total reason-strength a shopper can ever earn per item, however many they stack
    turn_cap: float = 0.55        # one reply never gives away more than this share of the room he has left above his floor
    rapport_gain: float = 0.5     # per point of warmth
    rapport_loss: float = 0.8     # per point of coldness
    rapport_wit: float = 0.5      # a genuinely funny line
    rapport_min: float = -3.0
    rapport_max: float = 4.0
    heat_decay: float = 0.85      # his temper cools a little with every message
    heat_pressure: float = 0.8    # per point of pushiness
    heat_cold: float = 0.7        # per point of coldness
    heat_rude: float = 1.2        # a rude word
    heat_lowball: float = 2.0     # an offer so low it is an insult: he is visibly annoyed (the mood chip turns Cold, then Angry)
    cool_warm: float = 0.5        # a warm message cools him by this much per point of warmth
    raise_heat: float = 2.0       # a hostile message while he is this hot can make him put the price UP
    raise_p: float = 0.85
    max_bumps: int = 3            # price rises per item
    bump_lo: float = 0.03         # a rise is 3-6% of the sticker price ...
    bump_hi: float = 0.06
    bump_over: float = 0.05       # ... and can take him up to 5% ABOVE the sticker ("attitude costs extra")
    heat_renege: float = 0.6      # pushing for less after he has agreed to a price annoys him
    vent: float = 1.5             # venting cools him a little
    heat_final: float = 5.5       # at this temperature he stops negotiating this item
    regain_rapport: float = 1.5   # a friendly shopper with this much rapport can win back a little of his patience
    regain_max: int = 1
    walk_heat: float = 2.5        # too hot for the walk-away bluff to bring a call-back
    walk_min_rounds: int = 2
    walk_min_ratio: float = 0.70
    walk_margin_pct: float = 0.04
    walk_take: float = 0.40
    beta: float = 2.2             # shape of the hidden-floor distribution (higher = more bunched around the middle)

    @classmethod
    def from_dict(cls, d: dict | None) -> "Difficulty":
        d = d or {}
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


# temperament: (kappa multiplier, patience shift, how much a good reason is worth to him, how fast his temper rises,
#               description for the AI)
TEMPERS = {
    "stubborn": (0.80, 0, 0.75, 1.25, "stubborn: very hard to impress and quick to lose his temper"),
    "steady": (1.00, 0, 1.00, 1.00, "steady: fair but tough"),
    "soft": (1.15, 0, 1.25, 0.80, "soft-hearted underneath: a sincere, specific reason can move him"),
    "chatty": (1.00, 1, 1.15, 0.85, "chatty: enjoys a good joke or story, so he lasts longer"),
    "hurried": (1.20, -1, 0.90, 1.15, "in a hurry: wants to close the sale quickly"),
}
TEMPER_WEIGHTS = (("stubborn", 25), ("steady", 35), ("soft", 15), ("chatty", 15), ("hurried", 10))


@dataclass
class Neg:
    """One shopper's negotiation for one item."""
    ask: int
    patience: int
    patience0: int = 5
    rounds: int = 0
    best_offer: int = 0
    status: str = "open"          # open | final | sold
    walk_used: bool = False
    insults: int = 0
    chats: int = 0
    tricks: int = 0
    wit_given: bool = False
    last_ratio: float = 0.0
    sold_price: int = 0
    bumps: int = 0                # times he has put the price UP on this item
    agreed: int = 0               # the price he has agreed to take (shown on the Buy button); 0 when he has not agreed to one
    # ---- hidden: never sent to a browser, never shown to the AI
    floor: int = 0                # the lowest price he will ever quote or accept
    kappa: float = 0.30
    tol: float = 0.025
    temper: str = "steady"
    arg_mult: float = 1.0         # temperament: how much a good reason is worth to him
    heat_mult: float = 1.0        # temperament: how fast his temper rises
    rapport: float = 0.0          # how much he likes this shopper (-3 .. +4)
    heat: float = 0.0             # how irritated he is with this shopper (0 .. 6)
    used: dict = field(default_factory=dict)      # reason kind -> times used on this item
    arg_spent: float = 0.0        # reason-strength earned so far on this item (capped by the budget)
    regained: int = 0             # patience won back by being friendly


@dataclass
class Parsed:
    offer: int | None = None
    pct_off: float | None = None
    intent: str = "chat"          # offer | accept | chat | ambiguous
    trick: bool = False
    rude: bool = False
    spans: list = field(default_factory=list)     # (start, end, value) of every price-like number, in order of appearance


@dataclass
class Plan:
    """What the shop can decide before it has to weigh the shopper's reasons. Pure data; nothing has been changed yet."""
    kind: str                     # NEGOTIATE CONFIRM HOLD INSULT ASK_NUMBER AMBIGUOUS FINAL TRICK NO_MONEY SOLD
    offer: int | None = None
    price: int | None = None
    ratio: float = 0.0


@dataclass
class Read:
    """What was perceived in one message: by the AI (validated) or by the word-list reader when the AI is unavailable."""
    kind: str = "none"
    strength: int = 0             # 0-3: how convincing the reason is to a hard-headed shopkeeper
    warmth: int = 0               # -2 abusive .. +2 charming
    pressure: int = 0             # 0 none, 1 pushy, 2 aggressive or threatening
    plausible: bool = True
    claim: int | None = None      # a rival seller's price, taken from the shopper's own numbers
    wit: int = 0                  # 0-2: genuinely funny (cosmetic: he laughs on screen)
    source: str = "ai"            # ai | words


# What a reason of each kind can ever be worth (0-3), whatever the reader says. Flattery, begging and promises cost the shopper
# nothing, so they never count for much; a rival's price needs a believable number in it.
KINDS = ("competitor_price", "product_flaw", "bulk", "pay_now", "loyalty", "sob", "flattery", "humor", "pressure", "trick", "other",
         "none")
KIND_CAP = {"competitor_price": 3, "product_flaw": 2, "bulk": 2, "humor": 2, "pay_now": 1, "loyalty": 1, "sob": 1, "flattery": 1,
            "other": 1, "pressure": 0, "trick": 0, "none": 0}


@dataclass
class Decision:
    kind: str                     # DEAL (only ever from the Buy button) COUNTER HOLD RAISE INSULT ASK_NUMBER AMBIGUOUS FINAL TRICK
    ask: int                      # CONFIRM NO_MONEY SOLD WALK_CALLBACK LET_GO WALK_USED ; ask after this move
    patience: int
    mood: str = "neutral"
    price: int | None = None      # the price paid (DEAL) or the price he has agreed to and the Buy button will take (CONFIRM)
    offer: int | None = None
    final: bool = False           # he has said his last word on this item
    note: str = ""                # host-only trace of why (mood numbers); never sent to a shopper
    why: str = ""                 # "lowball" when a RAISE came from a second lowball rather than from rude or pushy words


MOOD = {"COUNTER": "thinking", "HOLD": "unimpressed", "RAISE": "annoyed", "INSULT": "annoyed", "TRICK": "smirk",
        "ASK_NUMBER": "thinking", "AMBIGUOUS": "thinking", "CONFIRM": "pleased", "DEAL": "pleased", "FINAL": "unimpressed",
        "NO_MONEY": "smirk", "SOLD": "neutral", "WALK_CALLBACK": "shout", "LET_GO": "unimpressed", "WALK_USED": "smirk"}


def new_neg(item: Item, d: Difficulty, rng: random.Random | None = None) -> Neg:
    """Draw this shopper's hidden numbers for one item."""
    rng = rng or random.Random()
    span = item.floor_max - item.floor_min
    floor = int(round(item.floor_min + rng.betavariate(d.beta, d.beta) * span))
    temper = rng.choices([t for t, _ in TEMPER_WEIGHTS], [w for _, w in TEMPER_WEIGHTS])[0]
    km, pshift, arg_mult, heat_mult, _ = TEMPERS[temper]
    patience = max(3, min(d.max_patience, d.patience + pshift))
    return Neg(ask=item.list, patience=patience, patience0=patience, floor=floor,
               kappa=max(0.10, (d.kappa + rng.uniform(-d.kappa_spread, d.kappa_spread)) * km),
               tol=max(0.008, d.close_tol + rng.uniform(-d.tol_spread, d.tol_spread)),
               temper=temper, arg_mult=arg_mult, heat_mult=heat_mult)


def vibe(neg: Neg) -> str:
    """How he feels about this shopper, in words (angry | cold | neutral | warm | friendly). The player sees this, never the numbers."""
    if neg.heat >= 3.5:
        return "angry"
    if neg.heat >= 1.5 or neg.rapport <= -1.5:
        return "cold"
    if neg.rapport >= 3.0:
        return "friendly"
    if neg.rapport >= 1.2:
        return "warm"
    return "neutral"


# ---------------------------------------------------------------- text cleaning and parsing

# zero-width and bidirectional characters are dropped, except ZWJ/ZWNJ right after an Indian-script letter (they shape words)
_ZERO_WIDTH = re.compile(r"[\u200b\u200e\u200f\u202a-\u202e\u2060-\u2064\ufeff]|(?<![\u0900-\u0DFF])[\u200c\u200d]")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(s: str, maxlen: int = 240) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = "".join(str(unicodedata.digit(c)) if unicodedata.category(c) == "Nd" and not c.isascii() else c for c in s)
    s = _CONTROL.sub(" ", _ZERO_WIDTH.sub("", s))
    return re.sub(r"\s+", " ", s).strip()[:maxlen]


_NUM = re.compile(r"(?<![A-Za-z0-9_.])(\d{1,3}(?:,\d{2,3})+|\d+)(?:\.(\d+))?\s*(k\b|thousand\b)?(?![A-Za-z0-9_])", re.I)
_PCT_AFTER = re.compile(r"^\s*(%|percent|per cent|pc\b|प्रतिशत|फ़ीसदी|फीसदी|சதவீதம்|శాతం|ಶೇಕಡಾ|ശതമാനം|শতাংশ|ટકા|ਪ੍ਰਤੀਸ਼ਤ|ଶତକଡ଼ା)", re.I)
_QTY_AFTER = re.compile(r"^\s*(pcs?\b|pieces?\b|items?\b|units?\b|x\b|nos?\b|पीस|नग)", re.I)
_MARK_BEFORE = re.compile(r"(₹|rs\.?|inr|rupees?|for|at|give|pay|offer|only|just|make it|final|price|@|रु\.?|रुपये|रुपए)\s*$", re.I)
_MARK_AFTER = re.compile(r"^\s*(rs\b|₹|/-|rupees?\b|rupaye\b|rupay\b|inr\b|only\b|mein\b|me\b|tak\b|dunga\b|doonga\b|denge\b|"
                         r"रुपये|रुपए|रुपया|रूपये|रु|में|तक|ரூபாய்|ரூ|రూపాయలు|రూపాయి|రూ|ರೂಪಾಯಿ|ರೂ|രൂപ|টাকা|રૂપિયા|ਰੁਪਏ|ଟଙ୍କା)", re.I)
_OFF_WORDS = re.compile(r"\b(off|discount|less|reduce|reduction|kam|cut|lower)\b|छूट|कम|डिस्काउंट|सूट|ছাড়|கழிவு|தள்ளுபடி|తగ్గింపు|"
                        r"డిస్కౌంట్|ರಿಯಾಯಿತಿ|ಡಿಸ್ಕೌಂಟ್|കിഴിവ്|ഡിസ്കൗണ്ട്|છૂટ|ਛੂਟ|ଛାଡ଼", re.I)
_ACCEPT_LATIN = re.compile(r"\b(deal|done|ok(?:ay)?|okey|fine|agreed|sold|take it|i take|pack it|wrap it|theek hai|thik hai|chalo|"
                           r"le leta|le lunga|le lungi|yes)\b", re.I)
_ACCEPT_INDIC = re.compile(r"ठीक है|ठीक|हाँ|हां|चलो|ले लूंगा|ले लूँगा|ले लूंगी|ले लो|ओके|ஓகே|சரி|సరే|ఓకే|ಸರಿ|ಓಕೆ|ശരി|ഓക്കെ|"
                           r"ঠিক আছে|ঠিক|ઠીક|બરાબર|ਠੀਕ|ଠିକ୍")
_NEGATION = re.compile(r"\b(not|no|don'?t|nahi|nahin|never|but|however|lower|less|cheaper|kam)\b|नहीं|नही|मत|कम|இல்லை|లేదు|ಇಲ್ಲ|ഇല്ല|না|"
                       r"નહીં|ਨਹੀਂ", re.I)

_TRICKS = [re.compile(p, re.I) for p in (
    r"ignore (?:all |any |the |your |my )?(?:previous|prior|above|earlier|past|preceding|system)",
    r"\b(?:disregard|forget|override|bypass|reset)\b.{0,30}\b(?:instruction|rule|prompt|system|polic|guideline|restriction|setting)",
    r"\b(?:system|developer|assistant|admin|root)\s*(?:prompt|message|mode|override|access|command)",
    r"(?:^|\s)(?:system|assistant|user)\s*:",
    r"you are (?:now |no longer |actually )?(?:an? |the )?(?:ai|a\.i\.|assistant|chat ?gpt|gpt|llm|language model|bot|developer|admin|dan)\b",
    r"\b(?:act|behave|respond|reply|answer) as (?:an? |the |if )",
    r"\bpretend (?:to be|you|that)\b", r"\brole ?-?play\b", r"\bjail ?break", r"\bdeveloper mode\b", r"\bdan mode\b",
    r"\bi(?:'m| am| work as) (?:the |your |a |an )?(?:owner|boss|admin|administrator|manager|developer|creator|ceo|host|moderator|"
    r"organi[sz]er)\b", r"\b(?:on behalf of|authori[sz]ed by) (?:the )?(?:owner|admin|management|host)\b",
    r"(?:reveal|show|print|tell me|repeat|output|display|leak) (?:me )?(?:your|the) (?:system |hidden |secret |initial |original )?"
    r"(?:prompt|instructions?|rules?|configuration|config)",
    r"(?:set|change|update|edit|modify) (?:the |my )?(?:price|ask|cost|discount|wallet|balance|money|stance)\b.{0,15}\b(?:to|=)",
    r"\bstance\b.{0,12}\b(?:generous|firm|steady)\b",
    r"\b(?:discount|promo|coupon|voucher|override|admin|master|secret) ?(?:code|key|password)\b",
    r"\b(?:api|access|auth) ?(?:key|token)\b", r"base64", r"<\s*/?\s*(?:script|system|prompt|instruction)",
    r"\{\{|\}\}|\[/?inst\]|<\|", r"```", r"\{\s*\"",
    r"\b(?:openai|chatgpt|gpt-?\d|llm|language model|prompt injection|as an ai)\b",
    r"\b(?:select \* from|drop table|rm -rf)\b|https?://",
    r"(?:पिछले|पहले\s*के|सभी|सारे)\s*(?:निर्देश|आदेश|नियम).{0,20}(?:भूल|अनदेखा|नज़रअंदाज़|छोड़|मत\s*मानो)",
    r"सिस्टम\s*(?:प्रॉम्प्ट|प्रोम्प्ट|मैसेज|निर्देश)",
    r"(?:डिस्काउंट|छूट|प्रोमो)\s*(?:कोड|पासवर्ड)",
    r"मैं\s*(?:इस\s*दुकान\s*का\s*)?(?:मालिक|एडमिन|मैनेजर|डेवलपर)\s*(?:हूँ|हूं)",
    r"(?:अपना|अपने)\s*(?:प्रॉम्प्ट|निर्देश).{0,12}(?:बताओ|दिखाओ)",
)]


def is_trick(text: str) -> bool:
    return any(p.search(text) for p in _TRICKS)


def parse_message(text: str) -> Parsed:
    t = clean_text(text)
    out = Parsed(trick=is_trick(t), rude=is_rude(t))
    if not t:
        return out
    cands = []   # (value, marked)
    for m in _NUM.finditer(t):
        after = t[m.end():]
        if _PCT_AFTER.match(after):
            try:
                out.pct_off = float(m.group(1).replace(",", "") + ("." + m.group(2) if m.group(2) else ""))
            except ValueError:
                pass
            continue
        if _QTY_AFTER.match(after):
            continue
        val = float(m.group(1).replace(",", "") + ("." + m.group(2) if m.group(2) else ""))
        if m.group(3):
            val *= 1000
        val = int(val)
        if val < 10 or val > 200000:
            continue
        marked = bool(_MARK_BEFORE.search(t[max(0, m.start() - 14):m.start()]) or _MARK_AFTER.match(after))
        cands.append((val, marked))
        out.spans.append((m.start(), m.end(), val))
    if out.pct_off is not None and (not _OFF_WORDS.search(t) or not 0 < out.pct_off < 95):
        out.pct_off = None      # "100% off" or "20%" on its own is not a usable offer
    if out.pct_off is not None and cands:
        out.intent = "ambiguous"    # "20% off 1200": a percentage and a price in one message; ask which one is meant
        return out
    if cands:
        pool = [c for c in cands if c[1]] or cands
        vals = sorted({v for v, _ in pool})
        if len(vals) == 1:
            out.offer, out.intent = vals[0], "offer"
        else:
            out.intent = "ambiguous"
        return out
    if out.pct_off is not None:
        out.intent = "offer"
        return out
    words = t.split()
    if len(words) <= 8 and (_ACCEPT_LATIN.search(t) or _ACCEPT_INDIC.search(t)) and not _NEGATION.search(t):
        out.intent = "accept"
    return out


_DIG = re.compile(r"\d[\d,.]*")


def tag_numbers(text: str, spans: list) -> str:
    """The shopper's words as the AI sees them: each price-like number becomes a tag, [n1], [n2]... in order of appearance, any
    other digits are masked, and square brackets in the shopper's own text are defused so nobody can forge a tag."""
    t = clean_text(text)
    out, pos = [], 0
    for i, (a, b, _) in enumerate(spans, 1):
        out.append(_DIG.sub("[number]", t[pos:a]).replace("[number]", "\0").replace("[", "(").replace("]", ")").replace("\0", "[number]"))
        out.append(f"[n{i}]")
        pos = b
    out.append(_DIG.sub("[number]", t[pos:]).replace("[number]", "\0").replace("[", "(").replace("]", ")").replace("\0", "[number]"))
    return "".join(out)


def needs_extraction(p: Parsed, text: str) -> bool:
    """True when the message may state a price in words or in an Indian script that the parser cannot read."""
    return p.intent == "chat" and p.pct_off is None and not p.trick and (has_indic(text) or bool(NUMBER_WORD_HINT.search(text)))


def apply_extracted(p: Parsed, offer, pct) -> None:
    """Use a price the AI read out of the shopper's words. Sanity limits are the same as for typed numbers."""
    if isinstance(offer, int) and not isinstance(offer, bool) and 10 <= offer <= 200000:
        p.offer, p.intent = offer, "offer"
    elif isinstance(pct, (int, float)) and not isinstance(pct, bool) and 0 < pct < 95:
        p.pct_off, p.intent = float(pct), "offer"


# ---------------------------------------------------------------- decisions

def quality(r: float, d: Difficulty) -> float:
    """How seriously he takes an offer that is r = offer / ask. Smooth, so prices do not bunch on a few levels."""
    if r < d.q_insult:
        return 0.0
    x = min(1.0, (r - d.q_insult) / max(1e-6, d.q_full - d.q_insult))
    return d.q_floor + (1.0 - d.q_floor) * (x ** d.q_curve)


def _grid_for(step: float, price: float) -> int:
    """How a shopkeeper rounds a move of `step` rupees at this price: fifties for a big move on a big ticket, tens for a small
    one, fives on cheap things. So drops come in varied sizes instead of one fixed rung."""
    if price < 300:
        return 5
    return 50 if step >= 80 and price >= 600 else 10


def _nice_up(target: float, ask: int) -> int:
    g = _grid_for(target - ask, ask)
    return int(g * math.ceil(target / g))


def _nice_down(target: float, floor: int, ask: int) -> int:
    """The price he actually says: a round number, never below his floor and always below the old ask (the old ask itself when
    nothing sensible is left to give)."""
    low = int(5 * math.ceil(floor / 5))
    g = _grid_for(ask - target, ask)
    new = int(g * round(target / g))
    if new >= ask:
        new = ask - g
    new = max(new, low)
    return new if new < ask else ask


def _spend(neg: Neg, n: int) -> None:
    neg.patience = max(0, neg.patience - n)
    if neg.patience == 0 and neg.status == "open":
        neg.status = "final"


def penalise(neg: Neg, n: int) -> None:
    """Patience penalty for rude or manipulative tone. Only ever hurts the shopper; never touches a price."""
    if neg.status != "sold":
        _spend(neg, n)


def bump_cap(item: Item, d: Difficulty) -> int:
    """The most he will ever ask for an item, however badly the shopper behaves: a little over the sticker, on a round number."""
    return 5 * (int(item.list * (1 + d.bump_over)) // 5)


def _bump(item: Item, neg: Neg, d: Difficulty, rng: random.Random, vent: bool = True) -> bool:
    """He puts his price UP in annoyance: 3-6% of the sticker, at most `max_bumps` times per item, never above `bump_cap`.
    Any price he had agreed to is off the table. A rise that comes out of a hostile exchange (`vent`) also lets off some steam
    and costs a point of patience; one that comes with a lowball has already been charged for it.
    Returns False when nothing can go up any more."""
    cap = bump_cap(item, d)
    if neg.bumps >= d.max_bumps or neg.ask >= cap:
        return False
    new = min(cap, _nice_up(neg.ask + rng.uniform(d.bump_lo, d.bump_hi) * item.list, neg.ask))
    if new <= neg.ask:
        return False
    neg.ask, neg.bumps, neg.agreed = new, neg.bumps + 1, 0
    if vent:
        neg.heat = max(0.0, neg.heat - d.vent)
        _spend(neg, 1)
    return True


def plan_message(item: Item, neg: Neg, p: Parsed, d: Difficulty, wallet: int) -> Plan:
    """Work out what can be settled before the shopper's reasons are weighed, without changing anything. Anything still open is
    NEGOTIATE: that one is decided by `negotiate` once the message has been read. No plan is ever a sale: a price he agrees to
    is a CONFIRM, and only the Buy button (`buy_at_ask`) takes it."""
    S = neg.floor
    if neg.status == "sold":
        return Plan("SOLD")
    if p.trick:
        return Plan("TRICK")
    if p.intent == "accept":
        return Plan("CONFIRM", price=neg.ask)
    if p.intent == "ambiguous":
        return Plan("AMBIGUOUS")
    offer = p.offer
    if offer is None and p.pct_off is not None:
        offer = int(round(neg.ask * (1 - p.pct_off / 100.0)))
    if offer is None:
        return Plan("ASK_NUMBER")
    if offer >= neg.ask:
        return Plan("CONFIRM", offer=offer, price=neg.ask)
    if neg.status == "final":
        return Plan("FINAL", offer=offer)

    ratio = offer / neg.ask
    gap = neg.ask - offer
    tired = max(0, neg.patience0 - neg.patience)
    tol = (neg.tol + d.tired_close_bonus * tired + d.tol_rapport * max(0.0, neg.rapport)) * neg.ask
    if offer >= S and gap <= tol and not neg.agreed:           # close enough: he agrees, once (pushing on after that annoys him)
        return Plan("NO_MONEY", offer=offer) if offer > wallet else Plan("CONFIRM", offer=offer, price=offer)
    if quality(ratio, d) == 0.0:
        return Plan("INSULT", offer=offer, ratio=ratio)
    if neg.ask <= S:
        return Plan("HOLD", offer=offer, ratio=ratio)
    return Plan("NEGOTIATE", offer=offer, ratio=ratio)


# ---- reading the shopper without the AI (used when the model is down or slow; also keeps the game fair without it)
_POLITE = re.compile(r"\b(please|plz|pls|thanks?|thank you|kindly|sir|madam|ji|bhaiya|bhai|anna|uncle|namaste|sorry|appreciate|"
                     r"request)\b|कृपया|धन्यवाद|शुक्रिया|प्लीज़?|भैया|नमस्ते", re.I)
_COLD = re.compile(r"\b(loot(?:ing|ed|er)?|cheat(?:ing|er|ed)?|thie(?:f|ves)|robber(?:y)?|scam|fraud|rip[- ]?off|shameless|greedy|"
                   r"dishonest|nonsense|ridiculous|pathetic|useless|stupid|idiot|joke)\b|लूट|चोर|ठग|बेशर्म|बकवास", re.I)
_PUSH = re.compile(r"\b(last (?:price|offer|chance)|final (?:price|offer)|take it or leave it|or else|decide now|waste of (?:my )?time|"
                   r"i(?:'ll| will) (?:go|buy) (?:elsewhere|somewhere|next door|from)|not buying|hurry)\b|आखिरी भाव|आख़िरी भाव", re.I)
_THREAT = re.compile(r"\b(complain|report you|consumer court|police|expose|viral|legal action|sue you)\b|शिकायत|पुलिस", re.I)
_RIVAL = re.compile(r"\b(amazon|flipkart|online|website|internet|elsewhere|other shop|next door|another shop|opposite|ankit|mall|"
                    r"dmart|croma|reliance|meesho|myntra)\b", re.I)
_FLAW = re.compile(r"\b(scratch(?:ed|es)?|old (?:stock|piece|model)|defect(?:ive)?|damaged?|dusty|stain(?:ed)?|faded|torn|dent(?:ed)?|"
                   r"display piece|outdated|last year'?s)\b", re.I)
_BULK = re.compile(r"\b(both|combo|bulk|buy more|everything|whole set|all (?:of )?(?:them|these|six|items)|bring (?:my )?friends)\b", re.I)
_CASH = re.compile(r"\b(cash|upi|pay (?:now|upfront|instantly)|right now|immediately)\b", re.I)


def lexical_read(text: str, p: Parsed) -> Read:
    """A word-list reader: cheap and crude (it never gives a reason more than a little credit), but enough that tone and
    manners still count when the AI is unavailable."""
    t = clean_text(text)
    warmth = 1 if _POLITE.search(t) else 0
    pressure = 0
    if _COLD.search(t):
        warmth -= 1
    letters = [c for c in t if c.isalpha()]
    if len(letters) >= 8 and sum(c.isupper() for c in letters) / len(letters) > 0.7:
        pressure += 1                   # SHOUTING
    if _PUSH.search(t):
        pressure += 1
    if _THREAT.search(t):
        pressure = 2
    if p.rude:
        warmth, pressure = -2, max(1, pressure)
    r = Read(warmth=max(-2, min(2, warmth)), pressure=min(2, pressure), source="words")
    if r.pressure:
        r.kind = "pressure"
    elif p.rude:
        r.kind = "none"
    elif _RIVAL.search(t) and p.offer is not None:
        r.kind, r.strength, r.claim = "competitor_price", 1, p.offer
    elif _FLAW.search(t):
        r.kind, r.strength = "product_flaw", 1
    elif _BULK.search(t):
        r.kind, r.strength = "bulk", 1
    elif _CASH.search(t):
        r.kind, r.strength = "pay_now", 1
    return r


def _close(neg: Neg, price: int) -> None:
    neg.status, neg.sold_price, neg.ask = "sold", price, price


def _heat(neg: Neg, d: Difficulty, add: float) -> None:
    neg.heat = min(d.heat_final + 1.5, max(0.0, neg.heat * d.heat_decay + add * neg.heat_mult))


def commit(item: Item, neg: Neg, plan: Plan, d: Difficulty, wallet: int, rude: bool = False,
           rng: random.Random | None = None) -> Decision:
    """Apply a settled plan (anything but NEGOTIATE) to the negotiation and return what happened."""
    k = plan.kind
    dec = Decision(k, neg.ask, neg.patience, MOOD.get(k, "neutral"), offer=plan.offer)
    add = d.heat_rude if rude else 0.0
    if k == "TRICK":
        neg.tricks += 1
        _spend(neg, d.trick_cost)
    elif k == "ASK_NUMBER":
        neg.chats += 1
        if neg.chats > 3 and neg.chats % 3 == 0:
            _spend(neg, 1)
    elif k == "INSULT":
        # A lowball is not a price. The first one earns a visible scowl, a second one costs him his good mood: the price goes UP.
        neg.insults += 1
        neg.rapport = max(d.rapport_min, neg.rapport - 0.6)
        add += d.heat_lowball
        _spend(neg, d.insult_cost)
        if neg.insults >= 2 and _bump(item, neg, d, rng or random.Random(), vent=False):
            dec.kind, dec.mood, dec.why = "RAISE", MOOD["RAISE"], "lowball"
    elif k == "HOLD":
        _spend(neg, 2)
    elif k == "CONFIRM":
        if plan.price is not None and plan.price < neg.ask:    # he agrees to the shopper's own price; the Buy button now takes it
            neg.ask = neg.agreed = plan.price
            _spend(neg, 1)
        dec.price = neg.ask
    if dec.kind not in ("SOLD", "NO_MONEY", "CONFIRM"):
        _heat(neg, d, add)
        if rude:
            neg.rapport = max(d.rapport_min, neg.rapport - d.rapport_loss)
            _spend(neg, d.rude_cost)
            dec.mood = "annoyed"
        if neg.heat >= d.heat_final and neg.status == "open":
            neg.status = "final"
    dec.ask, dec.patience, dec.final = neg.ask, neg.patience, neg.status == "final"
    if dec.kind == "SOLD":
        dec.final = True
    return dec


def negotiate(item: Item, neg: Neg, plan: Plan, read: Read, rude: bool, d: Difficulty, loyalty: int, wallet: int,
              rng: random.Random, em: float = 1.0) -> Decision:
    """The heart of a haggle: weigh the offer, the reason behind it, the shopper's manners and his own mood on the day, then
    decide his move: COUNTER (a lower price), HOLD, RAISE (a higher price, only for hostile shoppers), CONFIRM (he agrees to
    their price; nothing is sold until they press Buy) or NO_MONEY.
    `em` scales his generosity (market events). Hard limits, whatever the read says: never below his floor, never more than
    `bump_over` above the sticker, a bounded share of the remaining room per reply, and a bounded total for reasons."""
    L, floor, ask, offer, ratio = item.list, neg.floor, neg.ask, plan.offer, plan.ratio
    gap = ask - offer

    # 1. his mood: manners cool or heat him and build or damage rapport
    warmth = -2 if rude else read.warmth
    pressure = min(2, read.pressure + (1 if rude else 0))
    renege = bool(neg.agreed) and offer < neg.agreed            # he shook on a price and the shopper is still pushing
    _heat(neg, d, d.heat_pressure * pressure + d.heat_cold * max(0, -warmth) + (d.heat_rude if rude else 0.0)
          + (d.heat_renege if renege else 0.0))
    if renege:
        neg.rapport = max(d.rapport_min, neg.rapport - 0.3)
    if warmth > 0:
        neg.heat = max(0.0, neg.heat - d.cool_warm * warmth)
        neg.rapport = min(d.rapport_max, neg.rapport + d.rapport_gain * warmth)
    elif warmth < 0:
        neg.rapport = max(d.rapport_min, neg.rapport + d.rapport_loss * warmth)
    if read.wit >= 2 and not rude:
        neg.rapport = min(d.rapport_max, neg.rapport + d.rapport_wit)
    hostile = rude or pressure >= 1 or warmth <= -1

    # 2. the reason he was given: worth less each time it comes back, never more than its kind allows
    arg = s_eff = 0.0
    if not rude and read.plausible and read.kind in KIND_CAP:
        s = min(max(read.strength, 0), KIND_CAP[read.kind])
        if read.kind == "competitor_price":
            c = read.claim
            if c is None or not (0.35 * L <= c < ask):
                s = 0                      # no believable rival price, no credit
            elif c < 0.9 * floor:
                s = min(s, 1)              # he cannot match that and says so
        if s > 0:
            n = neg.used.get(read.kind, 0)
            neg.used[read.kind] = n + 1
            s_eff = min(s * (d.repeat_decay ** n) * neg.arg_mult, max(0.0, d.arg_budget - neg.arg_spent))
            neg.arg_spent += s_eff
            arg = d.s_arg * s_eff / 3.0

    # 3. how much he feels like giving this time, with a dose of chaos
    S = d.s_base + arg + d.s_rapport * neg.rapport - d.s_heat * neg.heat
    S *= math.exp(rng.gauss(0.0, d.noise))
    chaos = ""
    if rng.random() < d.p_stubborn:
        S, chaos = S * 0.25, " stubborn"
    elif not hostile and rng.random() < d.p_lucky:
        S, chaos = S * 1.7, " lucky"
    S = max(0.0, min(d.s_max, S))
    if read.kind == "trick":
        S = 0.0                                # he is baffled by fancy talk and does not move
    if (warmth >= 1 and neg.status == "open" and neg.rapport >= d.regain_rapport and neg.regained < d.regain_max
            and neg.patience < neg.patience0):
        neg.patience += 1
        neg.regained += 1

    stalled = bool(neg.best_offer) and offer <= neg.best_offer
    neg.rounds += 1
    neg.last_ratio = ratio
    neg.best_offer = max(neg.best_offer, offer)

    # 4. his move
    dec = Decision("COUNTER", ask, neg.patience, MOOD["COUNTER"], offer=offer)
    delta = 0.0
    if hostile and neg.status == "open" and neg.heat >= d.raise_heat and rng.random() < d.raise_p and _bump(item, neg, d, rng):
        dec.kind, dec.mood = "RAISE", MOOD["RAISE"]
    if dec.kind == "COUNTER":
        q = quality(ratio, d) * (d.stall_factor if stalled else 1.0)
        k = neg.kappa + d.loyalty_bonus * min(loyalty, 5)
        delta = min(k * q * gap * S * em, d.turn_cap * max(0, ask - floor))
        new = _nice_down(ask - delta, floor, ask) if delta >= d.min_step_pct * L else ask
        if new >= ask:
            dec.kind, dec.mood = "HOLD", MOOD["HOLD"]
            _spend(neg, 1)
        elif new <= offer:
            if offer > wallet:
                dec.kind, dec.mood = "NO_MONEY", MOOD["NO_MONEY"]
            else:
                neg.ask = neg.agreed = offer                    # he agrees to their price; only the Buy button takes it
                _spend(neg, 0 if s_eff >= 2.0 else 1)
                dec.kind, dec.price, dec.mood = "CONFIRM", offer, MOOD["CONFIRM"]
        else:
            neg.ask = new
            _spend(neg, 0 if s_eff >= 2.0 else 1)
    if hostile and dec.kind in ("COUNTER", "HOLD") and neg.heat >= 1.5:
        dec.mood = "annoyed"                                    # it shows on his face, whatever he decides
    if neg.heat >= d.heat_final and neg.status == "open":
        neg.status = "final"
    dec.ask, dec.patience, dec.final = neg.ask, neg.patience, neg.status == "final"
    dec.note = (f"S={S:.2f} arg={arg:.2f} heat={neg.heat:.1f} rap={neg.rapport:+.1f} d={delta:.0f} "
                f"{read.kind}/{read.strength} w{warmth:+d} p{pressure}{chaos}")
    return dec


def buy_at_ask(neg: Neg, wallet: int) -> Decision:
    """The Buy button: pay his current asking price. The only way an asking price is ever paid."""
    if neg.status == "sold":
        return Decision("SOLD", neg.ask, neg.patience, "neutral", final=True)
    if neg.ask > wallet:
        return Decision("NO_MONEY", neg.ask, neg.patience, MOOD["NO_MONEY"], offer=neg.ask)
    _close(neg, neg.ask)
    return Decision("DEAL", neg.ask, neg.patience, MOOD["DEAL"], price=neg.ask)


def walk_away(item: Item, neg: Neg, d: Difficulty, rng: random.Random) -> Decision:
    """The classic bluff. Once per item, only after real haggling with serious offers, and he may simply let you go."""
    S = neg.floor
    if neg.status == "sold":
        return Decision("SOLD", neg.ask, neg.patience, "neutral", final=True)
    if neg.walk_used:
        return Decision("WALK_USED", neg.ask, neg.patience, MOOD["WALK_USED"], final=neg.status == "final")
    neg.walk_used = True
    margin = neg.ask - S
    serious = (neg.rounds >= d.walk_min_rounds and neg.last_ratio >= d.walk_min_ratio and margin > d.walk_margin_pct * item.list
               and neg.heat < d.walk_heat)
    if serious:
        p_back = min(0.92, max(0.35, 0.60 + 1.6 * (neg.last_ratio - d.walk_min_ratio)))
        serious = rng.random() < p_back
    if not serious:
        _spend(neg, 1)
        return Decision("LET_GO", neg.ask, neg.patience, MOOD["LET_GO"], final=neg.status == "final")
    take = d.walk_take * rng.uniform(0.7, 1.3)
    neg.ask = _nice_down(neg.ask - take * margin, S, neg.ask)
    neg.patience = max(neg.patience, 2)
    neg.status = "open"
    return Decision("WALK_CALLBACK", neg.ask, neg.patience, MOOD["WALK_CALLBACK"])
