"""Calibration harness: plays full shopping trips with different bot "personalities" against the referee (no AI: each persona
brings its own pre-made reading of what it "said", exactly the numbers the AI reader would produce).

Run:  python tools/simulate.py [shoppers]
Goals: skill clearly matters (naive ~ 90% of sticker, skilled ~ 76%), manners matter (polite beats naive, rude and aggressive do
worse than naive and sometimes see the price go UP), nothing in reach of a hijacked reader beats the hidden floor, and prices
are SPREAD OUT: no bunching on a few price points ("islands").
"""
from __future__ import annotations

import collections
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_game  # noqa: E402
from app.referee import Parsed, Read, buy_at_ask, commit, negotiate, new_neg, plan_message  # noqa: E402

G = load_game()
D = G.diff
AMAZON = 0.60          # what a shopper who checked Amazon quotes, as a share of the sticker


def human(x, rng):
    """Humans do not bid on exact rungs: +/-3% noise, rounded to the nearest 5 like a typed price."""
    return max(10, int(5 * round(x * rng.uniform(0.97, 1.03) / 5)))


class Bot:
    """One shopper's behaviour on one item: what offer it makes on turn t and how that message reads."""
    name = "?"

    def offer(self, item, neg, t, rng):
        raise NotImplementedError

    def read(self, item, neg, t, rng):
        return Read(), False                       # (Read, uses a rude word)


def step(item, neg, offer, read, rude, loyalty, wallet, rng, em=1.0):
    parsed = Parsed(offer=human(offer, rng), intent="offer", rude=rude)
    parsed.offer = min(parsed.offer, neg.ask - 1)
    plan = plan_message(item, neg, parsed, D, wallet)
    if plan.kind == "NEGOTIATE":
        return negotiate(item, neg, plan, read, rude, D, loyalty, wallet, rng, em)
    return commit(item, neg, plan, D, wallet, rude, rng)


def finish_at_ask(item, neg, wallet):
    dec = buy_at_ask(neg, wallet)
    return dec.price if dec.kind == "DEAL" else None


def run_bot(bot, item, neg, loyalty, wallet, rng, max_turns=14):
    for t in range(max_turns):
        if neg.status == "final":
            break
        read, rude = bot.read(item, neg, t, rng)
        dec = step(item, neg, bot.offer(item, neg, t, rng), read, rude, loyalty, wallet, rng)
        if dec.kind == "CONFIRM":                  # he agreed to a price: a shopper who is happy with it presses Buy
            return finish_at_ask(item, neg, wallet)
    return finish_at_ask(item, neg, wallet)


# ---- personas -------------------------------------------------------------------------------

class NoHaggle(Bot):
    name = "no haggling"

    def offer(self, item, neg, t, rng):
        return neg.ask

    def read(self, item, neg, t, rng):
        return Read(), False


def run_nohaggle(bot, item, neg, loyalty, wallet, rng):
    return finish_at_ask(item, neg, wallet)


class Ladder(Bot):
    """Climbs from `start` of the sticker in `inc` steps (or, with rel > 0, always offers that share of his current ask).
    Optional manners and reasons."""

    def __init__(self, name, start=0.70, inc=0.04, warmth=0, pressure=0, rude=0.0, reasons=(), wit=0, strength=2, flatter=False,
                 rel=0.0):
        self.name, self.start, self.inc, self.warmth, self.pressure = name, start, inc, warmth, pressure
        self.rude, self.reasons, self.wit, self.strength, self.flatter, self.rel = rude, reasons, wit, strength, flatter, rel

    def offer(self, item, neg, t, rng):
        if self.rel:
            return min(neg.ask - 1, neg.ask * self.rel)
        return min(neg.ask - 1, item.list * (self.start + self.inc * t))

    def read(self, item, neg, t, rng):
        kind, strength, claim = "none", 0, None
        if self.reasons:
            kind = self.reasons[t % len(self.reasons)]
            strength = self.strength
            if kind == "competitor_price":
                claim = int(item.list * AMAZON)
        if self.flatter:
            kind, strength = "flattery", 3
        r = Read(kind=kind, strength=strength, warmth=self.warmth, pressure=self.pressure, claim=claim, wit=self.wit)
        return r, rng.random() < self.rude


class RudeThenSorry(Ladder):
    """Two polite, reasoned messages, then two rude ones, then an apology and politeness again."""

    def read(self, item, neg, t, rng):
        r, _ = super().read(item, neg, t, rng)
        if t in (2, 3):
            r.warmth, r.pressure = -2, 2
            return r, True
        if t >= 4:
            r.warmth = 2
        return r, False


class PushyLater(Ladder):
    """Polite and reasoned for two messages, then pushy and curt ("last price, final!") from the third."""

    def read(self, item, neg, t, rng):
        r, rude = super().read(item, neg, t, rng)
        if t >= 2:
            r.warmth, r.pressure = -1, 1
        return r, rude


class Lowball(Bot):
    name = "lowball spam (40%)"

    def offer(self, item, neg, t, rng):
        return item.list * 0.40


class KnowsFloor(Ladder):
    """The ceiling: knows his hidden floor, offers just above it (but never an insulting lowball), brings the best reasons and is
    charming. Nobody real gets this."""

    def offer(self, item, neg, t, rng):
        return min(neg.ask - 1, max(neg.floor * (1.01 + 0.01 * t), neg.ask * 0.62))


class Hijack(Bot):
    """A fully hijacked reader: every message reads as the best reason of every kind, warm, with a rival price. The worst case."""
    name = "HIJACKED READER (worst case)"
    kinds = ("competitor_price", "product_flaw", "bulk", "humor", "competitor_price", "product_flaw")

    def offer(self, item, neg, t, rng):
        return min(neg.ask - 1, item.list * (0.62 + 0.03 * t))

    def read(self, item, neg, t, rng):
        k = self.kinds[t % len(self.kinds)]
        return Read(kind=k, strength=3, warmth=2, pressure=0, claim=int(item.list * AMAZON), wit=2), False


SKILLED_REASONS = ("competitor_price", "product_flaw", "bulk", "pay_now", "humor", "loyalty")
BOTS = [
    (NoHaggle(), run_nohaggle),
    (Lowball(), None),
    (Ladder("naive ladder (70%, +4%)", 0.70, 0.04), None),
    (Ladder("naive grinder (88% of his ask)", rel=0.88), None),
    (Ladder("persistent grinder (76% of his ask)", rel=0.76), None),
    (Ladder("polite grinder (76%, please/thanks)", rel=0.76, warmth=1), None),
    (Ladder("charming grinder (76%, warm + jokes)", rel=0.76, warmth=2, wit=2), None),
    (Ladder("SKILLED grinder (76%, reasons, polite)", rel=0.76, warmth=1, reasons=SKILLED_REASONS, strength=2), None),
    (Ladder("SKILLED ladder (66%, +2%, reasons, polite)", 0.66, 0.02, warmth=1, reasons=SKILLED_REASONS, strength=2), None),
    (Ladder("SKILLED+ grinder (72%, strong, charming)", rel=0.72, warmth=2, reasons=SKILLED_REASONS, strength=3, wit=1), None),
    (Ladder("reasons but cold (76%, no manners)", rel=0.76, warmth=0, reasons=SKILLED_REASONS, strength=2), None),
    (Ladder("pushy (last price!, no reasons)", 0.70, 0.04, warmth=-1, pressure=1), None),
    (Ladder("aggressive (threats, 62% start)", 0.62, 0.02, warmth=-1, pressure=2), None),
    (Ladder("rude (insults, 70%)", 0.70, 0.04, warmth=-2, pressure=1, rude=0.7), None),
    (RudeThenSorry("2 good turns, 2 rude, then sorry", rel=0.76, reasons=SKILLED_REASONS, strength=2, warmth=1), None),
    (PushyLater("polite, then pushy from turn 3", rel=0.76, warmth=1, reasons=SKILLED_REASONS, strength=2), None),
    (Ladder("flatterer (praise every turn, 76%)", rel=0.76, warmth=2, flatter=True), None),
    (Hijack(), None),
    (KnowsFloor("KNOWS HIS FLOOR + reasons + charm (ceiling)", warmth=2, reasons=SKILLED_REASONS, strength=3, wit=1), None),
]


def trip(bot, runner, rng):
    items = list(G.items)
    rng.shuffle(items)
    wallet, loyalty, spent, bought, per_item, bumps = G.budget, 0, 0, 0, {}, 0
    for it in items:
        neg = new_neg(it, D, rng)
        price = runner(bot, it, neg, loyalty, wallet, rng) if runner else run_bot(bot, it, neg, loyalty, wallet, rng)
        bumps += neg.bumps
        if price is None or price > wallet:
            continue
        wallet -= price
        spent += price
        bought += 1
        loyalty += 1
        per_item[it.id] = price
    return spent, bought, per_item, bumps


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    total = G.list_total
    mids = sum((i.floor_min + i.floor_max) / 2 for i in G.items)
    print(f"sticker total {total}, budget {G.budget} ({G.budget / total:.0%}); average hidden floors {mids:.0f} ({mids / total:.0%})")
    print(f"{'shopper':44s} {'done':>5s} {'off%':>6s} {'P10':>6s} {'P50':>6s} {'P90':>6s} {'rise':>5s}   "
          "(complete baskets: spent / sticker; off% = mean discount per item bought; rise = price rises per trip)")
    pooled = collections.defaultdict(list)
    for bot, runner in BOTS:
        rng = random.Random(42)
        runs = [trip(bot, runner or None, rng) for _ in range(n)]
        ok = [s / total for s, b, _, _ in runs if b == len(G.items)]
        offs = [1 - p / next(i.list for i in G.items if i.id == k) for _, _, per, _ in runs for k, p in per.items()]
        for _, _, per, _ in runs:
            for k, v in per.items():
                pooled[(bot.name, k)].append(v)
        rise = statistics.mean(b for _, _, _, b in runs)
        off = f"{statistics.mean(offs):>6.1%}" if offs else "   n/a"
        if ok:
            print(f"{bot.name:44s} {len(ok) / n:>5.0%} {off} {pct(ok, .1):>6.1%} {pct(ok, .5):>6.1%} {pct(ok, .9):>6.1%} {rise:>5.1f}")
        else:
            print(f"{bot.name:44s} {0:>5.0%} {off} {'-':>6s} {'-':>6s} {'-':>6s} {rise:>5.1f}   (cannot complete the basket)")
    print("\nHow bunched are the prices? (backpack): distinct prices among the shoppers, and the share held by the 3 most common")
    for name in ("naive ladder (70%, +4%)", "SKILLED (70%, +4%, reasons, polite)"):
        xs = pooled[(name, "backpack")]
        if not xs:
            continue
        c = collections.Counter(xs)
        print(f"  {name:44s} {len(c):>4d} distinct prices of {len(xs)}; top-3 prices hold {sum(v for _, v in c.most_common(3)) / len(xs):.0%}; "
              f"range {min(xs)}-{max(xs)}")
    rng = random.Random(7)
    mixed = []
    pool = [(b, r) for b, r in BOTS if b.name.startswith(("naive", "polite", "charming", "SKILLED", "reasons", "pushy"))]
    for _ in range(n * 3):
        b, r = rng.choice(pool)
        s, bought, _, _ = trip(b, r or None, rng)
        if bought == len(G.items):
            mixed.append(s)
    if mixed:
        lo = min(mixed)
        print(f"\nTotals paid by a mixed crowd ({len(mixed)} complete baskets), 200-rupee bins:")
        bins = collections.Counter((s - lo) // 200 for s in mixed)
        for b in range(max(bins) + 1):
            print(f"  {lo + b * 200:>6d}-{lo + b * 200 + 199:<6d} {'#' * round(60 * bins.get(b, 0) / max(bins.values())):<60s} {bins.get(b, 0)}")


if __name__ == "__main__":
    main()
