#!/usr/bin/env python
"""Rebuild the Bargain Bazaar audio sprite (static/sfx) from tools/sfx_sources.json.

    python tools/build_sfx_sprite.py            # download (if missing) + verify + build
    python tools/build_sfx_sprite.py --pin      # also write sha256 of newly downloaded files into the recipe
    python tools/build_sfx_sprite.py --no-sheet # skip the spectrogram contact sheet

Outputs: static/sfx/bazaar-sfx.mp3, static/sfx/bazaar-sfx.json, static/sfx/CREDITS.md and
tests/shots/sfx-real-clips.png. Source files are cached in tools/_sfx_cache/ (git-ignored).
The build is deterministic: same recipe + same cached sources + same ffmpeg => same bytes.
"""
import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import urllib.request

import numpy as np
from scipy import signal
from scipy.io import wavfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
CACHE = os.path.join(TOOLS, "_sfx_cache")
RECIPE = os.path.join(TOOLS, "sfx_sources.json")
OUT_DIR = os.path.join(ROOT, "static", "sfx")
SHEET = os.path.join(ROOT, "tests", "shots", "sfx-real-clips.png")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"

# ---------------------------------------------------------------- sources


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            with open(dest, "wb") as f:
                f.write(data)
            time.sleep(1.5)  # be polite to the hosts
            return
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(4 + 4 * attempt)
    raise RuntimeError("download failed: %s (%s)" % (url, last))


def ensure_source(sid, src, pin):
    path = os.path.join(CACHE, src["cacheFile"])
    if not os.path.exists(path):
        print("  downloading %s" % src["download"])
        download(src["download"], path)
    digest = sha256_file(path)
    want = src.get("sha256")
    if want:
        if digest != want:
            raise SystemExit("sha256 mismatch for %s: got %s, recipe says %s" % (sid, digest, want))
    elif pin:
        src["sha256"] = digest
    else:
        raise SystemExit("no sha256 pinned for %s (run with --pin once): %s" % (sid, digest))
    return path


def decode(path, rate):
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(rate), "-f", "f32le", "-"]
    out = subprocess.run(cmd, check=True, stdout=subprocess.PIPE).stdout
    return np.frombuffer(out, dtype="<f4").astype(np.float64)


# ---------------------------------------------------------------- loudness (ITU-R BS.1770 / EBU R128)


def k_weight(x, fs):
    f0, g, q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    k = math.tan(math.pi * f0 / fs)
    vh = 10 ** (g / 20)
    vb = vh**0.4996667741545416
    a0 = 1 + k / q + k * k
    b1 = [(vh + vb * k / q + k * k) / a0, 2 * (k * k - vh) / a0, (vh - vb * k / q + k * k) / a0]
    a1 = [1, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0]
    f0, q = 38.13547087602444, 0.5003270373238773
    k = math.tan(math.pi * f0 / fs)
    a0 = 1 + k / q + k * k
    a2 = [1, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0]
    y = signal.lfilter(b1, a1, x)
    return signal.lfilter([1, -2, 1], a2, y)


def integrated_lufs(x, fs):
    """Gated BS.1770-4 loudness; clips shorter than one 400 ms block use the whole clip as one block."""
    y = k_weight(x, fs)
    blk, step = int(0.4 * fs), int(0.1 * fs)
    if len(y) <= blk:
        return -0.691 + 10 * math.log10(max(np.mean(y**2), 1e-20))
    z = np.array([np.mean(y[i : i + blk] ** 2) for i in range(0, len(y) - blk + 1, step)])
    z = z[-0.691 + 10 * np.log10(np.maximum(z, 1e-20)) > -70]
    if len(z) == 0:
        return -70.0
    rel = -0.691 + 10 * math.log10(np.mean(z)) - 10
    z = z[-0.691 + 10 * np.log10(np.maximum(z, 1e-20)) > rel]
    return -0.691 + 10 * math.log10(np.mean(z))


def true_peak_db(x):
    return 20 * math.log10(max(np.max(np.abs(signal.resample_poly(x, 4, 1))), 1e-12))


def momentary_lufs(x, fs):
    """Loudest 400 ms K-weighted window (short clips: the whole clip), as tools/sfx_check.py measures each variant."""
    x = np.concatenate([np.zeros(int(0.1 * fs)), x, np.zeros(int(0.5 * fs))])
    idx = np.nonzero(np.abs(x) > 10 ** (-50 / 20))[0]
    a, z = idx[0], idx[-1]
    win = max(int(min(0.4, (z - a) / fs + 0.05) * fs), 1)
    cs = np.cumsum(np.insert(k_weight(x, fs) ** 2, 0, 0))
    return -0.691 + 10 * math.log10(((cs[win:] - cs[:-win]) / win).max() + 1e-12)


# ---------------------------------------------------------------- clip processing


def match_variants(processed, rate, cfg):
    """Level-match the variants of one sound. The game picks a variant at random, so they must not jump in volume:
    each variant is moved to the group's mean of (momentary LUFS + integrated LUFS) / 2, but never above the true-peak limit."""
    groups = {}
    for item in processed:
        groups.setdefault(item[0]["name"], []).append(item)
    for items in groups.values():
        if len(items) < 2:
            continue
        a = [0.5 * (momentary_lufs(y, rate) + integrated_lufs(y, rate)) for _, y, _ in items]
        room = [cfg["truePeakDb"] - true_peak_db(y) for _, y, _ in items]
        target = min(float(np.mean(a)), min(ai + ri for ai, ri in zip(a, room)))
        for (_, y, info), ai in zip(items, a):
            d = target - ai
            y *= 10 ** (d / 20)
            info["gain"] += d
            info["lufs"], info["tp"] = integrated_lufs(y, rate), true_peak_db(y)
            info["limited_by"] = "peak" if abs(cfg["truePeakDb"] - info["tp"]) < 0.05 else info["limited_by"]


def process_clip(x, rate, clip, cfg):
    a, b = int(round(clip["start"] * rate)), int(round(clip["end"] * rate))
    y = x[a:b].copy()
    speed = float(clip.get("speed", 1.0))
    if abs(speed - 1.0) > 1e-9:
        frac = int(round(speed * 1000))
        y = signal.resample_poly(y, 1000, frac)  # plain speed change (pitch follows)
    y = y - np.mean(y)  # DC offset
    n_in = int(round(cfg["fadeInMs"] * rate / 1000))
    n_out = int(round(clip.get("fadeOutMs", cfg["defaultFadeOutMs"]) * rate / 1000))
    env = np.ones(len(y))
    env[:n_in] *= 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, n_in, endpoint=False))
    env[-n_out:] *= 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, n_out, endpoint=False))
    y = y * env
    loud = integrated_lufs(y, rate)
    tp = true_peak_db(y)
    # aim the *decoded mp3* at targetLufs: libmp3lame @96 kbps measurably lowers the level (encoderCompensationDb)
    target = cfg["targetLufs"] + cfg.get("encoderCompensationDb", 0.0)
    limit = cfg["truePeakDb"] - tp
    gain = min(target - loud + float(clip.get("gainDb", 0.0)), limit)
    y = y * 10 ** (gain / 20)
    info = dict(lufs=integrated_lufs(y, rate), tp=true_peak_db(y), gain=gain, limited_by="peak" if gain >= limit - 1e-9 else "loudness")
    return y, info


# ---------------------------------------------------------------- outputs


def encode_mp3(sprite, rate, cfg, out_path):
    os.makedirs(CACHE, exist_ok=True)
    wav = os.path.join(CACHE, "sprite.wav")
    wavfile.write(wav, rate, sprite.astype(np.float32))
    cmd = [
        "ffmpeg", "-v", "error", "-y", "-i", wav, "-ac", "1", "-ar", str(rate),
        "-c:a", "libmp3lame", "-b:a", "%dk" % cfg["bitrateKbps"],
        "-fflags", "+bitexact", "-flags:a", "+bitexact", "-map_metadata", "-1", "-write_id3v2", "0",
        out_path,
    ]
    subprocess.run(cmd, check=True)


def write_manifest(path, cfg, clips_out, sources_out, offset):
    lines = ['{"version": 1, "file": %s, "rate": %d,' % (json.dumps(cfg["file"]), cfg["rate"])]
    if offset:
        lines.append(' "offset": %s,' % json.dumps(offset))
    lines.append(' "clips": {')
    names = list(clips_out)
    for i, name in enumerate(names):
        items = ", ".join(
            '{"t": %s, "d": %s, "id": %s}' % (json.dumps(c["t"]), json.dumps(c["d"]), json.dumps(c["id"])) for c in clips_out[name]
        )
        lines.append('  %s: [%s]%s' % (json.dumps(name), items, "," if i < len(names) - 1 else ""))
    lines.append(" },")
    lines.append(' "sources": [')
    for i, s in enumerate(sources_out):
        lines.append("  " + json.dumps(s, ensure_ascii=False) + ("," if i < len(sources_out) - 1 else ""))
    lines.append(" ]}")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def write_credits(path, recipe, used):
    srcs = recipe["sources"]
    by_kind = {"cc0": [], "cc-by": [], "non-cc": []}
    for sid in used:
        by_kind[srcs[sid]["kind"]].append(sid)

    def feeds(sid):
        names = []
        for c in recipe["clips"]:
            if c["source"] == sid and c["name"] not in names:
                names.append(c["name"])
        return ", ".join("`%s`" % n for n in names)

    def row(sid):
        s = srcs[sid]
        title = s["title"].replace("|", "/")
        if s.get("credit"):
            title += " (%s)" % s["credit"].replace("|", "/")
        return "| %s | %s | %s | [%s](%s) | [link](%s) |" % (feeds(sid), title, s["author"], s["license"], s["licenseUrl"], s["url"])

    head = "| Used for | Title | Author | Licence | Source |\n|---|---|---|---|---|"
    out = ["# Sound credits", ""]
    all_sped = [
        '"%s" is also sped up x%.2f' % (srcs[c["source"]]["title"], c["speed"]) for c in recipe["clips"] if c.get("speed", 1.0) != 1.0
    ]
    out.append(
        "Bargain Bazaar's voice reactions and shop sounds are real recordings from the Freesound community. "
        "Thank you to every creator! All clips were trimmed, faded and level-normalised for the game%s; nothing else was changed."
        % (" (" + "; ".join(all_sped) + ")" if all_sped else "")
    )
    out.append("")
    if by_kind["cc-by"]:
        out += ["## Creative Commons Attribution (CC BY) - credit required", ""]
        out += [head] + [row(s) for s in by_kind["cc-by"]] + [""]
        groups = {}
        for sid in by_kind["cc-by"]:
            s = srcs[sid]
            groups.setdefault((s["license"], s["licenseUrl"]), []).append(s["author"])
        who = []
        for (lic, url), authors in groups.items():
            names = list(dict.fromkeys(authors))
            names = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
            who.append("%s under %s (%s)" % (names, lic, url))
        sped = [
            '"%s" sped up x%.2f' % (srcs[c["source"]]["title"], c["speed"])
            for c in recipe["clips"]
            if c.get("speed", 1.0) != 1.0 and srcs[c["source"]]["kind"] == "cc-by"
        ]
        changes = "trimmed, faded and loudness-normalised" + ("; " + "; ".join(sped) if sped else "")
        out.append(
            "**Credit line:** Sound effects by %s, via Freesound.org. Edited for the game: %s." % ("; ".join(who), changes)
        )
        out.append("")
    if by_kind["cc0"]:
        out += ["## CC0 / Public Domain - no credit required (given anyway)", "", head] + [row(s) for s in by_kind["cc0"]] + [""]
    if by_kind["non-cc"]:
        out += [
            "## NOT Creative Commons - free-to-use licences (listed separately)",
            "",
            "These come from sites with their own free licence (no attribution required, credited anyway).",
            "",
            head,
        ] + [row(s) for s in by_kind["non-cc"]] + [""]
    out += [
        "## Licence texts",
        "",
        "- CC0 1.0 Universal: https://creativecommons.org/publicdomain/zero/1.0/",
        "- CC BY 3.0: https://creativecommons.org/licenses/by/3.0/",
        "- CC BY 4.0: https://creativecommons.org/licenses/by/4.0/",
        "",
        "_Generated by tools/build_sfx_sprite.py from tools/sfx_sources.json - edit the recipe, not this file._",
        "",
    ]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out))


def contact_sheet(path, items, rate):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cols = 4
    rows = (len(items) + cols - 1) // cols
    fig, axs = plt.subplots(rows, cols, figsize=(4.6 * cols, 2.3 * rows), squeeze=False)
    for ax in axs.flat:
        ax.axis("off")
    for ax, (label, y) in zip(axs.flat, items):
        ax.axis("on")
        ax.specgram(y, NFFT=512, Fs=rate, noverlap=384, cmap="magma", vmin=-130, vmax=-30)
        ax.set_ylim(0, 12000)
        ax.set_title("%s  (%.2fs)" % (label, len(y) / rate), fontsize=8)
        ax.tick_params(labelsize=6)
    fig.tight_layout()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=80)
    plt.close(fig)


# ---------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pin", action="store_true", help="write sha256 of downloaded sources into the recipe")
    ap.add_argument("--no-sheet", action="store_true")
    ap.add_argument("--recipe", default=RECIPE)
    args = ap.parse_args()

    with open(args.recipe, encoding="utf-8") as f:
        recipe = json.load(f)
    cfg = recipe["sprite"]
    rate = cfg["rate"]

    decoded = {}
    for sid, src in recipe["sources"].items():
        if not any(c["source"] == sid for c in recipe["clips"]):
            continue
        print("source %s" % sid)
        path = ensure_source(sid, src, args.pin)
        decoded[sid] = decode(path, rate)

    processed = []
    for clip in recipe["clips"]:
        y, info = process_clip(decoded[clip["source"]], rate, clip, cfg)
        processed.append((clip, y, info))
    match_variants(processed, rate, cfg)

    gap = np.zeros(int(round(cfg["gapSeconds"] * rate)))
    parts = [gap]
    pos = len(gap)
    clips_out, items, used, spans = {}, [], [], []
    for clip, y, info in processed:
        n = len(y)
        t, d = pos / rate, math.ceil(n / rate * 1000) / 1000
        variants = clips_out.setdefault(clip["name"], [])
        variants.append({"t": round(t, 3), "d": d, "id": clip["source"]})
        items.append(("%s #%d  %s" % (clip["name"], len(variants), clip["source"]), y))
        spans.append((clip["name"], clip["source"], pos, pos + n, info))
        if clip["source"] not in used:
            used.append(clip["source"])
        parts += [y, gap]
        pos += n + len(gap)
    sprite = np.concatenate(parts)

    os.makedirs(OUT_DIR, exist_ok=True)
    mp3 = os.path.join(OUT_DIR, cfg["file"])
    encode_mp3(sprite, rate, cfg, mp3)

    # report levels measured on the decoded mp3 (what the browser will play)
    dec = decode(mp3, rate)
    print("%-9s %-12s %6s %7s %8s %7s %7s  %s" % ("clip", "source", "dur", "LUFS", "momentary", "TP", "gain", "limited by"))
    group = {}
    for name, sid, a, e, info in spans:
        y = dec[a:e]
        lu, mo = integrated_lufs(y, rate), momentary_lufs(y, rate)
        group.setdefault(name, []).append((lu, mo))
        print("%-9s %-12s %6.3f %7.1f %8.1f %7.1f %7.1f  %s" % (name, sid, (e - a) / rate, lu, mo, true_peak_db(y), info["gain"], info["limited_by"]))
    for name, v in group.items():
        if len(v) > 1:
            print("variants of %-6s differ by %.1f LU (integrated), %.1f LU (momentary)" % (name, max(x[0] for x in v) - min(x[0] for x in v), max(x[1] for x in v) - min(x[1] for x in v)))
    print("decoded mp3: %.3f s (encoded sprite %.3f s)" % (len(dec) / rate, len(sprite) / rate))

    sources_out = []
    for sid in used:
        s = recipe["sources"][sid]
        sources_out.append(
            {"id": sid, "title": s["title"], "author": s["author"], "license": s["license"], "licenseUrl": s["licenseUrl"], "url": s["url"], "note": s["note"]}
        )
    write_manifest(os.path.join(OUT_DIR, os.path.splitext(cfg["file"])[0] + ".json"), cfg, clips_out, sources_out, cfg.get("offset", 0))
    write_credits(os.path.join(OUT_DIR, "CREDITS.md"), recipe, used)
    if not args.no_sheet:
        contact_sheet(SHEET, items, rate)
    if args.pin:
        with open(args.recipe, "w", encoding="utf-8", newline="\n") as f:
            json.dump(recipe, f, indent=1, ensure_ascii=False)
            f.write("\n")
    print("sprite %.2fs, %d bytes -> %s" % (len(sprite) / rate, os.path.getsize(mp3), mp3))


if __name__ == "__main__":
    sys.exit(main())
