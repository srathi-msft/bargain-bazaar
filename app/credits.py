"""The sound credits page (/credits): who made each recording Raju Anna plays, and under which licence.
Read from the manifest of the audio sprite (static/sfx/bazaar-sfx.json), so the page always matches the sounds that ship."""
from __future__ import annotations

import html
import json
from pathlib import Path


def _url(u) -> str:
    """Only plain web links are ever put on the page."""
    return u if isinstance(u, str) and u.startswith(("https://", "http://")) and " " not in u else ""


def _cell(s: dict, key: str) -> str:
    return html.escape(str(s.get(key) or ""))


def _link(url, text: str) -> str:
    u = _url(url)
    return f'<a href="{html.escape(u, quote=True)}" target="_blank" rel="noopener noreferrer">{html.escape(text)}</a>' if u else html.escape(text)


def credits_html(manifest: Path, title: str = "Bargain Bazaar", keeper: str = "Raju Anna") -> str:
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    sources = [s for s in data.get("sources", []) if isinstance(s, dict)]
    used = {}                                                 # source id -> the sounds it is used for
    for name, clips in (data.get("clips") or {}).items():
        for c in clips or []:
            if isinstance(c, dict):
                used.setdefault(c.get("id"), []).append(name)
    if sources:
        rows = "".join(
            "<tr><td>{use}</td><td>{title}</td><td>{author}</td><td>{lic}</td><td>{src}</td><td>{note}</td></tr>".format(
                use=html.escape(", ".join(sorted(set(used.get(s.get("id"), []))))), title=_cell(s, "title"), author=_cell(s, "author"),
                lic=_link(s.get("licenseUrl"), str(s.get("license") or "licence")), src=_link(s.get("url"), "source"), note=_cell(s, "note"))
            for s in sorted(sources, key=lambda s: (str(s.get("license") or "") != "CC0 1.0", str(s.get("title") or "").lower())))
        body = (f"<p>{html.escape(keeper)}'s voice reactions and shop sounds are real recordings shared on Freesound under Creative Commons "
                "licences. Thank you to every creator! Each clip was edited for the game as listed in the last column.</p>"
                "<table><thead><tr><th>Used for</th><th>Title</th><th>Author</th><th>Licence</th><th>Where</th><th>Changes</th></tr></thead>"
                f"<tbody>{rows}</tbody></table>")
    else:
        body = f"<p>All of {html.escape(keeper)}'s sounds are made by the browser itself: no recordings are used.</p>"
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>Sound credits - {html.escape(title)}</title><link rel=\"stylesheet\" href=\"/static/common.css\">"
            "<style>main{max-width:960px;margin:0 auto;padding:24px 16px 48px;line-height:1.5}h1{margin:.2em 0 .4em}"
            "table{width:100%;border-collapse:collapse;font-size:.92rem}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}"
            "a{color:var(--gold)}</style></head><body><main>"
            f"<p><a href=\"/\">&larr; {html.escape(title)}</a></p><h1>Sound credits</h1>{body}</main></body></html>")
