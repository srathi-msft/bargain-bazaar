"""Raju Anna's sound effects live in the browser (static/sfx.js) and are strictly optional: synthesised, with recorded Creative Commons
clips (one audio sprite) taking over the sounds that have them.
The server's part is small: it tells every browser the default level, and serves the script, the sprite and the credits page. Judging
how the sounds actually sound is done with tools/sfx_check.py and the host screen's "Sound check" button."""
import html
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.config import load_game, sound_defaults
from app.credits import credits_html

STATIC = Path(__file__).resolve().parent.parent / "static"
SPRITE = STATIC / "sfx" / "bazaar-sfx.json"
OK_LICENCES = {"CC0 1.0", "CC BY 4.0", "CC BY 3.0"}


def test_sound_is_on_by_default_for_the_host_screen_and_for_players():
    assert load_game().sound == {"host": "on", "players": "on"}


@pytest.mark.parametrize("raw,expected", [
    (None, {"host": "on", "players": "on"}),
    ("off", {"host": "on", "players": "on"}),
    ({"players": "off"}, {"host": "on", "players": "off"}),
    ({"host": "soft", "players": "loud"}, {"host": "soft", "players": "on"}),
])
def test_only_known_sound_levels_are_accepted(raw, expected):
    assert sound_defaults(raw) == expected


async def test_browsers_are_told_the_default_level(c):
    r = (await c.get("/api/public")).json()
    assert r["game"]["sound"] == {"host": "on", "players": "on"}


async def test_the_sound_engine_is_served_as_a_script(c):
    r = await c.get("/static/sfx.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]


@pytest.mark.parametrize("page,script", [("index.html", "player.js"), ("admin.html", "admin.js")])
def test_pages_load_the_sound_engine_before_their_own_script(page, script):
    html = (STATIC / page).read_text(encoding="utf-8")
    assert html.index("/static/sfx.js") < html.index(f"/static/{script}")


def test_the_sound_engine_only_ever_asks_the_game_itself_for_files():
    js = (STATIC / "sfx.js").read_text(encoding="utf-8")     # the page policy only allows scripts and media from the game itself
    assert not re.search(r"https?://|XMLHttpRequest|\beval\(|new Function", js)
    assert js.count("fetch(") == 2 and js.count("/static/sfx/") == 1      # the sprite's description and the sprite, nothing else


# ------------------------------------------------------------------ the recorded sounds (one audio sprite) and their credits
def _manifest():
    return json.loads(SPRITE.read_text(encoding="utf-8"))


def test_every_recorded_clip_is_for_a_known_sound_and_comes_from_a_credited_source():
    m = _manifest()
    sounds = set(re.findall(r'def\("(\w+)"', (STATIC / "sfx.js").read_text(encoding="utf-8")))
    sources = {s["id"]: s for s in m["sources"]}
    assert set(m["clips"]) <= sounds and {"hmm", "tsk", "hmph", "heh", "laugh", "shout", "raise", "wail", "deal"} <= set(m["clips"])
    for name, clips in m["clips"].items():
        assert clips, name
        for c in clips:
            assert c["id"] in sources and c["d"] > 0.03 and c["t"] >= 0, (name, c)
    for s in sources.values():
        assert s["license"] in OK_LICENCES and s["licenseUrl"].startswith("https://") and s["url"].startswith("https://"), s
        assert s["author"] and s["title"]


def test_the_sprite_is_one_small_file_and_every_clip_lies_inside_it():
    m = _manifest()
    mp3 = SPRITE.parent / m["file"]
    assert mp3.exists() and mp3.stat().st_size < 1_000_000           # one request per player, light on a phone
    if shutil.which("ffprobe"):
        secs = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp3)],
                                    capture_output=True, text=True, check=True).stdout)
        for name, clips in m["clips"].items():
            assert all(c["t"] + c["d"] <= secs + 0.05 for c in clips), name


def test_the_credits_file_names_every_author():
    text = (SPRITE.parent / "CREDITS.md").read_text(encoding="utf-8")
    for s in _manifest()["sources"]:
        assert s["author"] in text and s["url"] in text, s["id"]


async def test_the_credits_page_lists_every_recording_with_its_author_and_licence(c):
    r = await c.get("/credits")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    for s in _manifest()["sources"]:
        assert html.escape(s["author"]) in r.text and html.escape(s["url"], quote=True) in r.text and html.escape(s["license"]) in r.text


async def test_the_sprite_is_served_to_browsers(c):
    m = (await c.get("/static/sfx/bazaar-sfx.json")).json()
    r = await c.get("/static/sfx/" + m["file"])
    assert r.status_code == 200 and "audio" in r.headers["content-type"]


def test_credits_are_escaped_and_only_web_links_are_linked(tmp_path):
    f = tmp_path / "m.json"
    f.write_text(json.dumps({"clips": {"hmm": [{"t": 0, "d": 1, "id": "a"}]}, "sources": [
        {"id": "a", "title": "<script>x</script>", "author": "A & B", "license": "CC0 1.0", "licenseUrl": "javascript:alert(1)",
         "url": "https://freesound.org/x?a=1&b=2"}]}), encoding="utf-8")
    out = credits_html(f)
    assert "<script>x" not in out and "&lt;script&gt;" in out and "A &amp; B" in out and "javascript:" not in out
    assert 'href="https://freesound.org/x?a=1&amp;b=2"' in out and "<td>hmm</td>" in out


def test_credits_without_a_sprite_say_that_everything_is_synthesised(tmp_path):
    assert "made by the browser itself" in credits_html(tmp_path / "missing.json")
