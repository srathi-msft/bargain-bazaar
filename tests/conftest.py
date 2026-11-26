import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.config import Settings, load_game  # noqa: E402
from app.main import create_app  # noqa: E402
from app.referee import Read  # noqa: E402
from app.voice import PRICE, PRICE_KINDS, Perception, Reply, Voice  # noqa: E402

ADMIN = {"X-Admin-Key": "adm"}
G = load_game()


class Clock:
    def __init__(self, t: float = 1_800_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, s: float) -> None:
        self.t += s


def make_settings(tmp_path, **kw) -> Settings:
    base = dict(llm_provider="none", endpoint="", deployment="", api_version="2024-10-21", subscription="", api_key="",
                llm_rpm=40, port=0, public_url="https://bazaar.test", admin_key="adm", data_dir=Path(tmp_path))
    base.update(kw)
    return Settings(**base)


class FakeVoice(Voice):
    """A scriptable shopkeeper that never touches a model and records every turn it was asked about.

    `perceive` (serious offers) answers with the `Read` the test chose and canned lines. `respond` (settled turns) answers with one
    canned line. `offer` is the number the AI picks as the offer when a message has several, and the price `extract_offer` reads
    out of words; `wit` is how funny `respond` says the customer was. Tests may change any of these attributes between messages."""

    LINES = {"concede": f"Okay, {PRICE}, boss.", "hold": f"{PRICE} stays, boss.", "raise": f"Manners cost extra: {PRICE} now.",
             "agree": f"Fine, {PRICE}. Press Buy, boss."}

    def __init__(self, s, read=None, offer=None, pct=None, wit=0, lines=None):
        super().__init__(s)
        self.read = Read() if read is None else read
        self.offer, self.pct, self.wit_, self.lines = offer, pct, wit, {**self.LINES, **(lines or {})}
        self.turns = []
        self.extracted = []

    async def respond(self, t):
        self.turns.append(t)
        text = f"Okay, {PRICE}, boss." if t.kind in PRICE_KINDS else "Hahaha, be serious, boss."
        return Reply(text, "ai", self.wit_, 5)

    async def perceive(self, t):
        self.turns.append(t)
        return Perception(self.read, dict(self.lines), "ai", self.offer, 5)

    async def extract_offer(self, text):
        self.extracted.append(text)
        return self.offer, self.pct


class RollsLow(random.Random):
    """Every roll comes up at the bottom of its range: each chance-based move he might make (a rise, a call-back) happens."""

    def random(self):
        return 0.0


class Toks:
    async def get(self, force=False):
        return "tok"


def make_voice(handler, **kw):
    """The real `Voice` talking to a mock model service (an httpx handler) instead of the network."""
    s = make_settings(Path("."), llm_provider="azure", endpoint="http://mock", deployment="d", api_key="k", llm_rpm=600, **kw)
    return Voice(s, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), tokens=Toks())


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def voice(tmp_path):
    return Voice(make_settings(tmp_path))


@pytest.fixture
def app(tmp_path, clock, voice):
    return create_app(G, make_settings(tmp_path), voice, clock=clock, background=False, transcript=False,
                      rng=random.Random(11), auto_events=False)


@pytest.fixture
async def c(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        yield client


async def join(c, name="Asha Rao"):
    r = (await c.post("/api/join", json={"name": name})).json()
    assert r["ok"], r
    return {"X-Token": r["token"]}, r


async def start(c, minutes=10):
    r = (await c.post("/api/admin/start", headers=ADMIN, json={"minutes": minutes})).json()
    assert r["ok"]
    return r["snapshot"]


async def say(c, clock, h, item, msg):
    clock.advance(1.0)
    return (await c.post("/api/haggle", headers=h, json={"item_id": item, "message": msg})).json()


async def buy(c, clock, h, item):
    clock.advance(1.0)
    return (await c.post("/api/buy", headers=h, json={"item_id": item})).json()


async def walk(c, clock, h, item):
    clock.advance(1.0)
    return (await c.post("/api/walk", headers=h, json={"item_id": item})).json()


async def haggle_until_sold(c, clock, h, item, share=0.86, turns=14):
    """Offer `share` of his current ask each time; once he agrees to a price or says it is his final word, press Buy (the only
    thing that ever sells). Returns the sale's reply."""
    me = (await c.get("/api/me", headers=h)).json()["me"]
    for _ in range(turns):
        n = me["items"][item]
        r = await buy(c, clock, h, item) if (n["status"] == "final" or n["agreed"]) else await say(c, clock, h, item, str(int(n["ask"] * share)))
        me = r["me"]
        if r["deal"]:
            return r
    raise AssertionError(f"no sale after {turns} messages: {r}")


def player_of(app, who=0):
    """The server-side player (hidden negotiation state included) who joined n-th: tests set up and inspect it directly."""
    return list(app.state.store.players.values())[who]
