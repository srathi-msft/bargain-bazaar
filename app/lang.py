"""Script and language helpers. The game's default language is English; shoppers may write in any Indian language."""
from __future__ import annotations

import re
import unicodedata

SCRIPT_RANGES = {
    "devanagari": (0x0900, 0x097F),
    "bengali": (0x0980, 0x09FF),
    "gurmukhi": (0x0A00, 0x0A7F),
    "gujarati": (0x0A80, 0x0AFF),
    "odia": (0x0B00, 0x0B7F),
    "tamil": (0x0B80, 0x0BFF),
    "telugu": (0x0C00, 0x0C7F),
    "kannada": (0x0C80, 0x0CFF),
    "malayalam": (0x0D00, 0x0D7F),
}

SCRIPT_LABEL = {
    "latin": "Latin letters (English, or romanised Hindi or another Indian language)",
    "devanagari": "Devanagari script (Hindi or Marathi)",
    "bengali": "Bengali script",
    "gurmukhi": "Gurmukhi script (Punjabi)",
    "gujarati": "Gujarati script",
    "odia": "Odia script",
    "tamil": "Tamil script",
    "telugu": "Telugu script",
    "kannada": "Kannada script",
    "malayalam": "Malayalam script",
}

INDIC_RE = re.compile("[\u0900-\u0DFF]")

# Romanised Hindi function words: used to tell "English" from "Hinglish" so the shopkeeper answers in kind.
HINDI_LATIN = re.compile(
    r"\b(hai|hain|nahi|nahin|kya|toh|ka|ke|ki|ko|mein|yeh|woh|aap|tum|tumhara|mera|meri|mere|tera|teri|hoon|hoga|"
    r"karo|kar|bolo|batao|dena|deta|lena|lo|bas|abhi|mat|kuch|koi|sab|bahut|bohot|kitna|kaun|kaise|kyun|aur|"
    r"lekin|magar|sirf|wahi|yahi|isse|usse|ho|ya|pehle|leke|hamara|humara|dekho|suno|chhodo|jao|aao|raho|"
    r"wapas|waapas|thoda|zyada|dedo|de|do)\b", re.I)

# Money written in words (we never let the AI do this, and use it to decide when to ask the AI to read a shopper's price).
NUMBER_WORD_HINT = re.compile(
    r"\b(hundred|thousand|lakh|sau|saw|hazaar|hazar|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
    r"(?:ek|do|teen|char|paanch|panch|chhe|chhah|saat|aath|nau)\s*sau)\b", re.I)


def script_of(ch: str) -> str:
    o = ord(ch)
    for name, (lo, hi) in SCRIPT_RANGES.items():
        if lo <= o <= hi:
            return name
    if ch.isascii() and ch.isalpha():
        return "latin"
    return ""


def detect_script(text: str) -> str:
    """The script the shopper mostly wrote in. Anything that is not clearly Indic counts as Latin."""
    counts: dict[str, int] = {}
    for ch in text:
        s = script_of(ch)
        if s:
            counts[s] = counts.get(s, 0) + 1
    total = sum(counts.values())
    if not total:
        return "latin"
    indic = {k: v for k, v in counts.items() if k != "latin"}
    if indic:
        top = max(indic, key=indic.get)
        if indic[top] / total >= 0.25:
            return top
    return "latin"


def has_indic(text: str) -> bool:
    return bool(INDIC_RE.search(text))


def indic_scripts(text: str) -> set[str]:
    """The Indian scripts that appear in `text` (empty for plain Latin text)."""
    return {s for s in (script_of(ch) for ch in text) if s and s != "latin"}


def wrote_hindi_like(text: str) -> bool:
    """True if the shopper used a non-Latin script or at least two romanised Hindi words."""
    return has_indic(text) or len(HINDI_LATIN.findall(text)) >= 2


def is_letter_or_mark(ch: str) -> bool:
    return unicodedata.category(ch)[0] in ("L", "M")
