"""Loads game.json and environment settings (no third-party dependencies)."""
from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from .referee import Difficulty, Item

ROOT = Path(__file__).resolve().parent.parent
SOUND_LEVELS = ("on", "soft", "off")


def load_dotenv(path: Path | None = None) -> None:
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


@dataclass
class Game:
    title: str
    shop_name: str
    shopkeeper: str
    currency: str
    budget: int
    duration_min: int
    max_players: int
    items: list[Item]
    diff: Difficulty
    sound: dict = field(default_factory=lambda: {"host": "on", "players": "on"})   # default level of Raju Anna's sound effects

    @property
    def list_total(self) -> int:
        return sum(i.list for i in self.items)

    def item(self, item_id: str) -> Item | None:
        return next((i for i in self.items if i.id == item_id), None)

    def public(self) -> dict:
        """Everything a browser may know. Floors are never included."""
        return {
            "title": self.title, "shop_name": self.shop_name, "shopkeeper": self.shopkeeper,
            "currency": self.currency, "budget": self.budget, "duration_min": self.duration_min,
            "list_total": self.list_total, "patience": self.diff.patience, "sound": dict(self.sound),
            "items": [{"id": i.id, "name": i.name, "emoji": i.emoji, "list": i.list} for i in self.items],
        }


def sound_defaults(raw) -> dict:
    """Default sound level for the host screen and for players: 'on', 'soft' or 'off' (anything else means 'on')."""
    raw = raw if isinstance(raw, dict) else {}
    return {k: (raw.get(k) if raw.get(k) in SOUND_LEVELS else "on") for k in ("host", "players")}


def load_game(path: Path | None = None) -> Game:
    raw = json.loads((path or ROOT / "config" / "game.json").read_text(encoding="utf-8"))
    items = [Item(**i) for i in raw["items"]]
    for i in items:
        if not (0 < i.floor_min <= i.floor_max < i.list):
            raise ValueError(f"item {i.id}: need 0 < floor_min <= floor_max < list price")
    return Game(raw["title"], raw["shop_name"], raw["shopkeeper"], raw["currency"], int(raw["budget"]),
                int(raw.get("duration_min", 15)), int(raw.get("max_players", 150)), items,
                Difficulty.from_dict(raw.get("difficulty")), sound_defaults(raw.get("sound")))


@dataclass
class Settings:
    llm_provider: str
    endpoint: str
    deployment: str
    api_version: str
    subscription: str
    api_key: str
    llm_rpm: int
    port: int
    public_url: str
    admin_key: str
    data_dir: Path
    allowed_account: str = ""        # the only Azure account this app may sign in with (so another signed-in account is never used by mistake)
    reasoning_effort: str = ""       # for reasoning models: minimal | low | medium | high ("" = not sent)
    llm_timeout: float = 8.0         # seconds a top-priority AI call may take before the ready-made line is used


def load_settings() -> Settings:
    load_dotenv()
    e = os.environ.get
    provider = (e("LLM_PROVIDER") or "none").lower()
    # Each provider reads only its own key variables, so an unrelated key in your environment is never picked up by mistake.
    key_vars = {"azure": ("LLM_API_KEY", "AZURE_OPENAI_API_KEY"), "claude": ("LLM_API_KEY", "ANTHROPIC_API_KEY"),
                "gemini": ("LLM_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")}.get(provider, ())
    api_key = next((e(k) for k in key_vars if e(k)), "")
    endpoint = e("LLM_ENDPOINT") or e("AZURE_OPENAI_ENDPOINT") or ""
    if not endpoint and provider == "gemini":
        endpoint = "https://generativelanguage.googleapis.com/v1beta"
    if not endpoint and provider == "claude" and api_key:
        endpoint = "https://api.anthropic.com"
    return Settings(
        llm_provider=provider,
        endpoint=endpoint.rstrip("/"),
        deployment=e("LLM_MODEL") or e("AZURE_OPENAI_DEPLOYMENT") or "",
        api_version=e("AZURE_OPENAI_API_VERSION") or "2024-10-21",
        subscription=e("AZURE_SUBSCRIPTION_ID") or "",
        api_key=api_key,
        llm_rpm=int(e("LLM_RPM") or 40),
        port=int(e("PORT") or 8000),
        public_url=(e("PUBLIC_URL") or "").rstrip("/"),
        admin_key=e("ADMIN_KEY") or secrets.token_urlsafe(9),
        data_dir=Path(e("DATA_DIR") or ROOT / "data"),
        allowed_account=(e("AZURE_ALLOWED_ACCOUNT") or "").strip(),
        reasoning_effort=(e("AZURE_OPENAI_REASONING_EFFORT") or "").strip().lower(),
        llm_timeout=float(e("LLM_TIMEOUT_S") or 8.0),
    )
