"""Builds a captioned video of every Raju Anna sound (his face for the mood, the sound's name), so you can listen without starting the game.

  python tools/sfx_sampler.py [out.mp4]        # default: tests/shots/Anna-Sound-Sampler.mp4
  python tools/sfx_sampler.py --synth          # the synthesised sounds instead of the recordings

The audio is rendered by static/sfx.js through the same output chain the game uses, at the "On" level. A sound with several
recordings is played once per recording ("take 1/2", "take 2/2"): in the game one of them is picked at random.
"""
from __future__ import annotations

import os
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sfx_check import RATE, load_sprite, render  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "tests" / "shots"
W, H = 960, 540
FONTS = r"C:\Windows\Fonts"


def font(name, size):
    return ImageFont.truetype(f"{FONTS}\\{name}", size)


def wrap(draw, text, fnt, width):
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=fnt) <= width:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    return lines + ([cur] if cur else [])


def main() -> None:
    out = Path(next((a for a in sys.argv[1:] if not a.startswith("--")), SHOTS / "Anna-Sound-Sampler.mp4"))
    SHOTS.mkdir(parents=True, exist_ok=True)
    work = SHOTS / "_sampler"
    work.mkdir(exist_ok=True)
    page_html = work / "page.html"
    page_html.write_text('<!doctype html><link rel="stylesheet" href="../../../static/common.css"><style>html,body{background:transparent!important}</style>'
                         '<body><div id="a" data-anna style="width:330px;height:372px"></div>'
                         '<script src="../../../static/avatar.js"></script><script src="../../../static/sfx.js"></script>', encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch(channel=os.environ.get("BAZAAR_BROWSER", "msedge") or None)
        pg = b.new_page(viewport={"width": 400, "height": 420}, device_scale_factor=1)
        pg.goto(page_html.as_uri())
        load_sprite(pg)
        names = []
        for n in pg.evaluate("Sfx.names()"):
            if n["name"] == "pop":
                continue
            takes = n["variants"] if n["real"] and n["variants"] > 1 else 1
            for v in range(takes):
                names.append({**n, "variant": v, "label": n["label"] + (f"  (take {v + 1}/{takes})" if takes > 1 else "")})
        lengths, cues, t = {}, [], 0.5
        for n in names:
            _, ends = render(pg, [{"t": 0, "sound": n["name"], "variant": n["variant"]}], 3.0, True)
            lengths[n["name"]] = ends[0]
            cues.append({"t": t, "sound": n["name"], "variant": n["variant"]})
            t += ends[0] + 0.8
        total = t + 0.3
        data, _ = render(pg, cues, total, True)
        for mood in sorted({n["mood"] or "neutral" for n in names}):
            pg.evaluate("m => Anna.mood(document.getElementById('a'), m)", mood)
            pg.wait_for_timeout(450)
            pg.locator("#a").screenshot(path=str(work / f"anna-{mood}.png"), omit_background=True)
        b.close()

    pcm = (np.clip(data, -1, 1) * 32767).astype("<i2")
    wav = work / "sampler.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(pcm.tobytes())

    title, big, small, badge = font("seguibl.ttf", 34), font("segoeuib.ttf", 46), font("segoeui.ttf", 28), font("segoeuib.ttf", 26)
    frames = []
    for i, (n, cue) in enumerate(zip(names, cues)):
        img = Image.new("RGB", (W, H))
        px = img.load()
        for y in range(H):                                          # indigo gradient, like the game
            k = y / H
            for x in range(W):
                px[x, y] = (int(20 + 13 * k), int(13 + 8 * k), int(43 + 34 * k))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 8], fill=(255, 194, 51))
        d.text((40, 28), "RAJU ANNA: SOUND CHECK", font=title, fill=(255, 194, 51))
        d.text((W - 40, 34), f"{i + 1} / {len(names)}", font=badge, fill=(185, 172, 216), anchor="ra")
        face = Image.open(work / f"anna-{n['mood'] or 'neutral'}.png").convert("RGBA")
        face.thumbnail((330, 372))
        img.paste(face, (50, 112), face)
        y = 190
        for line in wrap(d, n["label"], big, W - 460 - 40):
            d.text((420, y), line, font=big, fill=(255, 243, 214))
            y += 62
        d.text((420, y + 14), f"his face: {n['mood'] or 'no face change'}", font=small, fill=(185, 172, 216))
        path = work / f"frame-{i:02d}.png"
        img.save(path)
        start = 0.0 if i == 0 else cue["t"] - 0.3
        end = (cues[i + 1]["t"] - 0.3) if i + 1 < len(cues) else total
        frames.append((path, end - start))

    listing = work / "frames.txt"
    listing.write_text("".join(f"file '{p.as_posix()}'\nduration {dur:.3f}\n" for p, dur in frames) + f"file '{frames[-1][0].as_posix()}'\n", encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-i", str(wav), "-r", "15",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "24", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
                    str(out)], check=True)
    print(f"saved {out} ({out.stat().st_size / 1e6:.2f} MB, {total:.1f} s)")


if __name__ == "__main__":
    main()
