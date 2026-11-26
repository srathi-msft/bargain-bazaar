"""Renders every Raju Anna sound effect offline in Edge (no speakers needed) and checks it.

  python tools/sfx_check.py            # table, plus tests/shots/sfx-sampler.wav and sfx-spectrograms.png
  python tools/sfx_check.py --strict   # exit 1 if a sound is silent, clipping, longer than declared or far louder/quieter than the rest
  python tools/sfx_check.py --tune     # re-balance the loudness tables at the top of sfx.js (CAL for synthesised, CAL_REC for recorded)
  python tools/sfx_check.py --synth    # ignore the recorded sprite and check the synthesised sounds

The sounds are synthesised in static/sfx.js, and replaced by the recordings in static/sfx/ (when that sprite exists). This checks their
numbers (length, peak, loudness, brightness, and how far the variants of one recording differ); it cannot judge taste, so listen
with the host screen's "Sound check" button.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import wave
from pathlib import Path

import numpy as np
from playwright.sync_api import sync_playwright
from scipy.signal import lfilter

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "tests" / "shots"
SPRITE = ROOT / "static" / "sfx" / "bazaar-sfx.json"
RATE = 44100
AIM = {1: -28, 2: -25, 3: -23}           # aimed loudness (LUFS, momentary) by priority: routine voice sounds sit under the landmark ones
JS = """
async ({cues, dur, limiter}) => {
  const r = await Sfx.render(cues, dur, {limiter, rate: RATE});
  const u8 = new Uint8Array(r.data.buffer, r.data.byteOffset, r.data.byteLength);
  let bin = ''; const CH = 0x8000;
  for (let i = 0; i < u8.length; i += CH) bin += String.fromCharCode.apply(null, u8.subarray(i, i + CH));
  return { b64: btoa(bin), ends: r.ends };
}
""".replace("RATE", str(RATE))


def render(pg, cues, dur, limiter):
    r = pg.evaluate(JS, {"cues": cues, "dur": dur, "limiter": limiter})
    return np.frombuffer(base64.b64decode(r["b64"]), dtype="<f4").astype(np.float64), r["ends"]


def load_sprite(pg) -> int:
    """Hands the recorded sounds (static/sfx) to a bare test page the way the browser fetches them. Returns how many sounds have a
    recording (0 when there is no sprite or --synth was given)."""
    if "--synth" in sys.argv or not SPRITE.exists():
        return 0
    meta = json.loads(SPRITE.read_text(encoding="utf-8"))
    mp3 = (SPRITE.parent / meta["file"]).read_bytes()
    pg.evaluate("""async ({meta, b64}) => {
        const bin = atob(b64), u8 = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
        await Sfx.loadSpriteData(u8.buffer, meta);
    }""", {"meta": meta, "b64": base64.b64encode(mp3).decode()})
    return pg.evaluate("Sfx.names().filter(n => n.real).length")


def k_weight(x, fs=RATE):
    """ITU-R BS.1770 K-weighting (shelf plus high-pass), so loudness numbers roughly follow what the ear hears."""
    g, q, fc = 3.999843853973347, 0.7071752369554196, 1681.974450955533
    k = np.tan(np.pi * fc / fs); vh = 10 ** (g / 20); vb = vh ** 0.4996667741545416; a0 = 1 + k / q + k * k
    x = lfilter([(vh + vb * k / q + k * k) / a0, 2 * (k * k - vh) / a0, (vh - vb * k / q + k * k) / a0], [1, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0], x)
    q, fc = 0.5003270373238773, 38.13547087602444
    k = np.tan(np.pi * fc / fs); a0 = 1 + k / q + k * k
    return lfilter([1, -2, 1], [1, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0], x)


def measure(x, declared):
    db = lambda v: 20 * np.log10(max(float(v), 1e-9))
    peak = float(np.max(np.abs(x)))
    idx = np.where(np.abs(x) > 10 ** (-50 / 20))[0]
    if not len(idx) or not np.isfinite(x).all():
        return {"ok": False, "why": "silent or NaN", "peak": peak}
    a, z = idx[0], idx[-1]
    seg = x[a:z + 1]
    w = int(0.010 * RATE); n = max(1, len(seg) // w)
    ms = (seg[:n * w].reshape(n, w) ** 2).mean(axis=1) if len(seg) >= w else np.array([np.mean(seg ** 2)])
    rms = float(np.sqrt(ms[ms > ms.max() * 0.1].mean()))
    kx = k_weight(x)
    win = max(int(min(0.4, (z - a) / RATE + 0.05) * RATE), 1)
    cs = np.cumsum(np.insert(kx ** 2, 0, 0)); lufs = -0.691 + 10 * np.log10(((cs[win:] - cs[:-win]) / win).max() + 1e-12)
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))); fr = np.fft.rfftfreq(len(seg), 1 / RATE)
    return {"ok": True, "dur": (z - a) / RATE, "declared": declared, "peak": peak, "peak_db": db(peak), "rms_db": db(rms), "lufs": float(lufs),
            "centroid": float((spec * fr).sum() / spec.sum()), "dc": float(np.mean(x))}


def measure_all(pg):
    """Renders each sound alone through the real output chain and measures it (every variant of a recording); also works out the
    gain that would hit its aim."""
    rows, raw = [], {}
    for n in pg.evaluate("Sfx.names()"):
        got = []
        for v in range(max(1, n["variants"]) if n["real"] else 1):
            x, ends = render(pg, [{"t": 0.1, "sound": n["name"], "variant": v}], 4.0, True)
            got.append((measure(x, ends[0] - 0.1), x))
        okay = [g for g in got if g[0]["ok"]]
        m, x = sorted(okay, key=lambda g: g[0]["lufs"])[len(okay) // 2] if okay else got[0]
        m = dict(m, name=n["name"], label=n["label"], prio=n["prio"], g=n["g"], real=n["real"], variants=len(got))
        if okay:
            lufs = [g[0]["lufs"] for g in okay]
            m["spread"] = max(lufs) - min(lufs)
            m["aim"] = AIM.get(m["prio"], -25) if m["name"] != "pop" else -28
            room = -6 - max(g[0]["peak_db"] for g in okay)                        # peaks stay under -6 dBFS
            adj = min(m["aim"] - float(np.mean(lufs)), room)
            m["limited"] = room < m["aim"] - float(np.mean(lufs)) - 0.05           # a sharp transient: the peak, not the aim, sets its level
            m["new_g"] = m["g"] * 10 ** (adj / 20)
            m["lufs"] = float(np.mean(lufs))
        rows.append(m)
        raw[n["name"]] = x
    return rows, raw


def main() -> int:
    strict = "--strict" in sys.argv
    SHOTS.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch(channel=os.environ.get("BAZAAR_BROWSER", "msedge") or None)
        pg = b.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.set_content("<!doctype html><title>sfx</title>")
        pg.add_script_tag(path=str(ROOT / "static" / "sfx.js"))
        n_real = load_sprite(pg)
        print(f"recorded sounds: {n_real} (the rest are synthesised)" if n_real else "all sounds synthesised (no recorded sprite loaded)")
        rows, raw = measure_all(pg)
        if "--tune" in sys.argv:                           # adjust the in-page gains until every sound hits its aim, then print them
            for i in range(10):
                worst = max((abs(m["lufs"] - m["aim"]) for m in rows if m["ok"] and not m["limited"]), default=0.0)
                print(f"tune pass {i}: worst miss {worst:.2f} LU")
                if worst < 0.5:
                    break
                pg.evaluate("m => Sfx.tune(m)", {m["name"]: m["new_g"] for m in rows if m["ok"]})
                rows, raw = measure_all(pg)
            for title, want in (("CAL", False), ("CAL_REC", True)):
                part = [m for m in rows if m["real"] == want]
                if part:
                    print("  const " + title + " = {\n    " + ", ".join(f"{m['name']}: {m['g']:.3f}" for m in part) + ",\n  };")
        # the whole set, one after another, through the real output chain (compressor included)
        cues, t = [], 0.4
        for m in rows:
            if m["name"] == "pop":
                continue
            cues.append({"t": t, "sound": m["name"]})
            t += m["declared"] + 0.7
        mix, _ = render(pg, cues, t + 0.5, True)
        b.close()

    print(f"{'sound':9} {'kind':>6} {'secs':>5} {'heard':>5} {'peak dB':>8} {'rms dB':>7} {'LUFS':>6} {'aim':>5} {'centroid':>9}  gain now -> suggested   (* = sharp transient: limited by its peak, so quieter than the aim)")
    bad = []
    for m in rows:
        if not m["ok"]:
            print(f"{m['name']:9} {m['why']}"); bad.append(m["name"] + ": " + m["why"]); continue
        kind = (f"rec{m['variants']}" if m["real"] else "synth") + ("*" if m["limited"] else "")
        print(f"{m['name']:9} {kind:>6} {m['declared']:5.2f} {m['dur']:5.2f} {m['peak_db']:8.1f} {m['rms_db']:7.1f} {m['lufs']:6.1f} {m['aim']:5.0f} {m['centroid']:8.0f}Hz  {m['g']:.3f} -> {m['new_g']:.3f}")
        if m["peak"] > 0.9: bad.append(f"{m['name']}: peak {m['peak']:.2f} is too close to clipping")
        if abs(m["lufs"] - m["aim"]) > 2 and not (m["limited"] and m["lufs"] < m["aim"]):
            bad.append(f"{m['name']}: {m['lufs']:.1f} LUFS, aimed for {m['aim']}")
        if m["real"] and m["spread"] > 4: bad.append(f"{m['name']}: its {m['variants']} recordings differ by {m['spread']:.1f} LU")
        if m["dur"] > m["declared"] + 0.15: bad.append(f"{m['name']}: rings {m['dur']:.2f}s but declares {m['declared']:.2f}s")
        if m["dur"] < 0.04: bad.append(f"{m['name']}: only {m['dur']:.3f}s long")
        if abs(m["dc"]) > 0.01: bad.append(f"{m['name']}: DC offset {m['dc']:.3f}")
    good = [m for m in rows if m["ok"] and m["name"] != "pop"]
    if good:
        lo, hi = min(m["lufs"] for m in good), max(m["lufs"] for m in good)
        print(f"loudness: quietest {lo:.1f}, loudest {hi:.1f} LUFS (routine voice sounds aim quieter than landmark ones)")
    pk = float(np.max(np.abs(mix)))
    print(f"sampler through the output chain: peak {20 * np.log10(max(pk, 1e-9)):.1f} dBFS, {len(mix) / RATE:.1f} s")
    if pk > 0.98: bad.append("the sampler clips")

    pcm = (np.clip(mix, -1, 1) * 32767).astype("<i2")
    with wave.open(str(SHOTS / "sfx-sampler.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(pcm.tobytes())
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        cols = 3; rws = int(np.ceil(len(good) / cols))
        fig, axes = plt.subplots(rws, cols, figsize=(15, 2.4 * rws), dpi=80)
        for ax, m in zip(axes.flat, good):
            x = raw[m["name"]][int(0.05 * RATE): int((0.1 + m["declared"] + 0.2) * RATE)]
            ax.specgram(x, NFFT=1024, Fs=RATE, noverlap=900, cmap="magma", vmin=-120, vmax=-35)
            ax.set_ylim(0, 9000); ax.set_title(f"{m['name']}  ({m['lufs']:.1f} LUFS)", fontsize=9); ax.tick_params(labelsize=7)
        for ax in list(axes.flat)[len(good):]:
            ax.axis("off")
        fig.tight_layout(); fig.savefig(SHOTS / "sfx-spectrograms.png"); plt.close(fig)
    except Exception as e:  # noqa: BLE001
        print("no spectrogram:", e)
    print(f"saved {SHOTS / 'sfx-sampler.wav'}")
    if errors:
        bad += [f"browser error: {e}" for e in errors]
    for line in bad:
        print("FAIL", line)
    print("OK" if not bad else f"{len(bad)} problem(s)")
    return 1 if (bad and strict) else 0


if __name__ == "__main__":
    sys.exit(main())

