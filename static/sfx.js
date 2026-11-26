/* Bargain Bazaar: Raju Anna's little sound effects.
   By default everything is synthesised with the Web Audio API: no audio files, nothing to download, nothing copyrighted.
   Optionally, recorded Creative Commons clips (one audio sprite, see static/sfx/CREDITS.md) replace the synthesised version of a
   sound when they load; any sound without a recording, and every sound when the sprite is missing, keeps its synthesised voice.
   Sound is strictly optional. If audio is missing, blocked or switched off, every call is a silent no-op and the game is unaffected. */
(() => {
  "use strict";
  const AC = window.AudioContext || window.webkitAudioContext;
  const OAC = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  const LEVELS = { off: 0, soft: 0.4, on: 1 };

  // ---------------------------------------------------------------- synth toolkit (works on live and offline contexts)
  const noiseBufs = new WeakMap();
  function noiseBuffer(c) {
    let b = noiseBufs.get(c);
    if (!b) {
      b = c.createBuffer(1, Math.floor(c.sampleRate * 1.5), c.sampleRate);
      const d = b.getChannelData(0);
      let s = 1234567;                                   // fixed seed: every sound is identical, live or rendered
      for (let i = 0; i < d.length; i++) { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; d[i] = s / 2147483648 - 1; }
      noiseBufs.set(c, b);
    }
    return b;
  }

  // Gain envelope: rise over att, hold, fade over rel (ending at t + dur).
  function env(c, t, dur, peak, att = 0.01, rel = 0.05) {
    const g = c.createGain(), a = Math.min(att, dur * 0.4), r = Math.min(rel, dur * 0.6);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(peak, t + a);
    g.gain.setValueAtTime(peak, t + dur - r);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    return g;
  }
  // Percussive envelope: instant attack, exponential decay.
  function perc(c, t, dur, peak, att = 0.003) {
    const g = c.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(peak, t + att);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    return g;
  }
  // Oscillator with an optional pitch glide (f0 to f1) and vibrato (depth in Hz). Connected to dest when given.
  function tone(c, dest, type, f0, f1, t, dur, o = {}) {
    const n = c.createOscillator();
    n.type = type;
    n.frequency.setValueAtTime(f0, t);
    if (f1 && f1 !== f0) n.frequency.exponentialRampToValueAtTime(f1, t + dur);
    if (o.detune) n.detune.value = o.detune;
    if (o.vib) {
      const l = c.createOscillator(), lg = c.createGain();
      l.frequency.value = o.vibHz || 5.5;
      lg.gain.value = o.vib;
      l.connect(lg); lg.connect(n.frequency);
      l.start(t); l.stop(t + dur + 0.05);
    }
    if (dest) n.connect(dest);
    n.start(t); n.stop(t + dur + 0.05);
    return n;
  }
  // A burst of filtered noise (breath, clicks, shutters).
  function puff(c, dest, t, dur, peak, o = {}) {
    const s = c.createBufferSource(), f = c.createBiquadFilter();
    s.buffer = noiseBuffer(c); s.loop = true;
    f.type = o.type || "bandpass"; f.Q.value = o.q || 1;
    f.frequency.setValueAtTime(o.f || 1000, t);
    if (o.f1) f.frequency.exponentialRampToValueAtTime(o.f1, t + dur);
    const g = o.flat ? env(c, t, dur, peak, o.att ?? 0.01, o.rel ?? dur * 0.4) : perc(c, t, dur, peak, o.att ?? 0.003);
    s.connect(f); f.connect(g); g.connect(dest);
    s.start(t, o.off || 0); s.stop(t + dur + 0.05);
  }
  // A struck bell: a few inharmonic partials, each ringing for a different time.
  function bell(c, dest, t, f, o = {}) {
    const parts = o.parts || [1, 2.76, 5.4, 8.93], amps = o.amps || [1, 0.5, 0.25, 0.12], dec = o.decay || 0.9;
    parts.forEach((r, i) => {
      if (f * r > c.sampleRate * 0.42) return;
      const d = dec / (1 + i * 0.8), n = tone(c, null, "sine", f * r, 0, t, d), g = perc(c, t, d, (o.gain ?? 0.3) * amps[i], 0.002);
      n.connect(g); g.connect(dest);
    });
  }
  const ping = (c, dest, t, f, g) => bell(c, dest, t, f, { parts: [1, 2.7], amps: [1, 0.3], decay: 0.16, gain: g });
  // A tongue click ("tsk").
  function click(c, dest, t, f, g, q = 3.5) {
    puff(c, dest, t, 0.05, g * 4, { f, q });
    const n = tone(c, null, "sine", 1100, 520, t, 0.035), e = perc(c, t, 0.035, g * 0.6, 0.002);
    n.connect(e); e.connect(dest);
  }
  // Marimba-like pluck.
  function mallet(c, dest, t, f, g, d = 0.2) {
    const a = tone(c, null, "sine", f, 0, t, d), ea = perc(c, t, d, g, 0.003), b = tone(c, null, "sine", f * 4, 0, t, d * 0.3), eb = perc(c, t, d * 0.3, g * 0.3, 0.002);
    a.connect(ea); ea.connect(dest); b.connect(eb); eb.connect(dest);
  }
  // Brass-like note: two detuned saws through a "wah" lowpass.
  function brass(c, dest, t, f, dur, o = {}) {
    const lp = c.createBiquadFilter(), g = env(c, t, dur, o.gain ?? 0.3, o.att ?? 0.04, o.rel ?? Math.min(0.09, dur * 0.4));
    lp.type = "lowpass"; lp.Q.value = o.q ?? 2;
    lp.frequency.setValueAtTime(o.c0 ?? 500, t);
    lp.frequency.linearRampToValueAtTime(o.c1 ?? 2400, t + Math.min(0.12, dur * 0.5));
    lp.frequency.exponentialRampToValueAtTime(o.c2 ?? 900, t + dur);
    lp.connect(g); g.connect(dest);
    for (const d of [-8, 8]) tone(c, lp, "sawtooth", f, o.droop ? f * o.droop : f, t, dur, { detune: d, vib: o.vib, vibHz: 5.2 });
  }

  // Raju Anna's voice: a sawtooth "vocal cord" through three vowel filters. f0 = [start, end] pitch, v to v2 = vowel morph.
  const VOW = {
    a: [[730, 1], [1090, 0.7], [2440, 0.35]],
    e: [[530, 1], [1840, 0.6], [2480, 0.35]],
    o: [[570, 1], [840, 0.6], [2410, 0.3]],
    u: [[320, 1], [800, 0.45], [2240, 0.25]],
    m: [[270, 1], [1000, 0.1], [2200, 0.05]],
  };
  const curves = {};
  function clipCurve(k) {
    if (!curves[k]) {
      const a = new Float32Array(257);
      for (let i = 0; i < 257; i++) { const x = i / 128 - 1; a[i] = Math.tanh(k * x) / Math.tanh(k); }
      curves[k] = a;
    }
    return curves[k];
  }
  function voice(c, dest, t, dur, o) {
    const A = VOW[o.v || "a"], B = VOW[o.v2 || o.v || "a"], f0 = o.f0 || [130, 130];
    const out = env(c, t, dur, o.gain ?? 0.5, o.att ?? 0.012, o.rel ?? Math.min(0.07, dur * 0.45)), sum = c.createGain();
    let head = sum;
    if (o.rough) {                                       // growl: fast tremolo
      const am = c.createGain(), lfo = c.createOscillator(), lg = c.createGain();
      am.gain.value = 1 - o.rough / 2;
      lfo.frequency.value = o.roughHz || 55; lg.gain.value = o.rough / 2;
      lfo.connect(lg); lg.connect(am.gain); lfo.start(t); lfo.stop(t + dur + 0.05);
      head.connect(am); head = am;
    }
    if (o.grit) { const ws = c.createWaveShaper(); ws.curve = clipCurve(o.grit); head.connect(ws); head = ws; }
    head.connect(out); out.connect(dest);
    const src = tone(c, null, "sawtooth", f0[0], f0[1], t, dur, { vib: o.vib, vibHz: o.vibHz || 5.5 });
    [5, 7, 9].forEach((q, k) => {
      const bp = c.createBiquadFilter(), g = c.createGain();
      bp.type = "bandpass"; bp.Q.value = q;
      bp.frequency.setValueAtTime(A[k][0], t);
      if (B !== A) bp.frequency.linearRampToValueAtTime(B[k][0], t + dur);
      g.gain.value = (o.boost ?? 7) * A[k][1];
      src.connect(bp); bp.connect(g); g.connect(sum);
    });
    if (o.breath) puff(c, out, t, Math.min(dur, 0.1), o.breath * 2.5, { f: B[1][0], q: 1.1, off: o.off || 0 });
  }

  // Rolling shutter: rattling noise sweeping up (opening) or down (closing).
  function shutter(c, dest, t, dur, down) {
    const am = c.createGain(), lfo = c.createOscillator(), lg = c.createGain(), e = env(c, t, dur, 0.9, 0.04, 0.15);
    am.gain.value = 0.6; lfo.type = "square"; lfo.frequency.value = 23; lg.gain.value = 0.4;
    lfo.connect(lg); lg.connect(am.gain); lfo.start(t); lfo.stop(t + dur + 0.05);
    e.connect(am); am.connect(dest);
    puff(c, e, t, dur, 4, { f: down ? 2600 : 320, f1: down ? 320 : 2600, q: 1.6, flat: true, att: 0.05, rel: 0.12 });
    puff(c, dest, t + dur - 0.02, 0.07, 3, { f: 700, q: 2 });
  }
  // Cash register: "ka" (clack), "ching" (bell), then a few coins.
  function register(c, dest, t, big) {
    puff(c, dest, t, 0.05, 3.5, { f: 1700, q: 0.9 });
    const n = tone(c, null, "sine", 160, 55, t, 0.08), e = perc(c, t, 0.08, 0.5, 0.002);
    n.connect(e); e.connect(dest);
    bell(c, dest, t + 0.09, 2349, { decay: 1.0, parts: [1, 2.32, 4.1, 6.3], amps: [1, 0.55, 0.3, 0.15], gain: 0.3 });
    const k = big ? 9 : 4;
    for (let i = 0; i < k; i++) ping(c, dest, t + 0.24 + i * 0.055 + ((i * 37) % 5) * 0.006, 2600 + ((i * 937) % 1900), 0.07 + (i % 3) * 0.015);
    if (big) bell(c, dest, t + 0.42, 3136, { decay: 0.9, parts: [1, 2.32, 4.1], amps: [1, 0.5, 0.25], gain: 0.2 });
  }

  // ---------------------------------------------------------------- the sounds (each fn schedules itself at t and returns its length in seconds)
  // Output level per sound, set with tools/sfx_check.py so that they sit at a similar loudness (routine voice sounds quietest).
  const CAL = {
    door: 0.253, open: 0.143, hmm: 0.046, tsk: 0.663, hmph: 0.110, heh: 0.083, laugh: 0.136, wail: 0.168, shout: 0.072, raise: 0.185,
    deal: 0.218, dealBig: 0.218, tada: 0.148, rush: 0.304, tight: 0.217, bell: 0.308, fanfare: 0.179, close: 0.115, pop: 0.250,
  };
  const SOUNDS = {};
  const def = (name, label, o, fn) => { SOUNDS[name] = { name, label, prio: 1, gap: 0.3, g: CAL[name] ?? 1, mood: "", ...o, fn }; };

  def("door", "Shop door chime (a shopper walks in)", { prio: 1, gap: 2.5 }, (c, o, t) => {
    const p = { decay: 0.55, parts: [1, 2, 3], amps: [1, 0.25, 0.1], gain: 0.28 };
    bell(c, o, t, 1319, p); bell(c, o, t + 0.17, 1047, { ...p, decay: 0.7 });
    return 0.95;
  });
  def("open", "Shutters roll up (the shop opens)", { prio: 3, gap: 0 }, (c, o, t) => {
    shutter(c, o, t, 0.62, false);
    bell(c, o, t + 0.66, 1568, { decay: 0.7, gain: 0.26 }); bell(c, o, t + 0.84, 2093, { decay: 0.9, gain: 0.26 });
    return 1.8;
  });
  def("hmm", "Hmm... (he is thinking: a counter-offer)", { prio: 1, gap: 0.5, cls: "voice", mood: "thinking" }, (c, o, t) => {
    voice(c, o, t, 0.13, { v: "m", f0: [118, 128], gain: 0.55, breath: 0.2 });
    voice(c, o, t + 0.2, 0.26, { v: "m", f0: [126, 168], gain: 0.6, vib: 4 });
    return 0.5;
  });
  def("tsk", "Tsk tsk (unimpressed: he holds his price)", { prio: 1, gap: 0.5, cls: "voice", mood: "unimpressed" }, (c, o, t) => {
    click(c, o, t, 2900, 0.3); click(c, o, t + 0.17, 2500, 0.25);
    return 0.32;
  });
  def("hmph", "Hmph! (annoyed)", { prio: 1, gap: 0.5, cls: "voice", mood: "annoyed" }, (c, o, t) => {
    puff(c, o, t, 0.16, 1.6, { f: 900, q: 1.1, att: 0.012 });
    voice(c, o, t + 0.01, 0.2, { v: "o", f0: [112, 78], gain: 0.55, rough: 0.5, breath: 0.1 });
    return 0.3;
  });
  def("heh", "Heh heh (smirk: nice try)", { prio: 1, gap: 0.5, cls: "voice", mood: "smirk" }, (c, o, t) => {
    voice(c, o, t, 0.08, { v: "e", f0: [175, 190], gain: 0.5, breath: 0.3 });
    voice(c, o, t + 0.13, 0.12, { v: "e", f0: [185, 205], gain: 0.55, breath: 0.3, off: 0.4 });
    return 0.35;
  });
  def("laugh", "Ha ha ha! (pleased, or you made him laugh)", { prio: 2, gap: 3, cls: "notable", mood: "pleased" }, (c, o, t) => {
    for (let i = 0; i < 4; i++) voice(c, o, t + i * 0.135, 0.1, { v: "a", f0: [215 - i * 12, 195 - i * 12], gain: 0.55 * (1 - i * 0.12), breath: 0.35, off: i * 0.2 });
    return 0.65;
  });
  def("wail", "Sad trombone (big discount: he is crying inside)", { prio: 2, gap: 3, cls: "notable", mood: "sobbing" }, (c, o, t) => {
    let at = t;
    [[233, 0.2], [220, 0.2], [208, 0.2], [196, 0.7]].forEach(([f, d], i) => {
      brass(c, o, at, f, d, { gain: 0.3, c0: 450, c1: 1700, c2: 700, droop: i === 3 ? 0.95 : 0, vib: i === 3 ? 5 : 0 });
      at += d;
    });
    return 1.4;
  });
  def("shout", "ARRE! (you walked away)", { prio: 2, gap: 1.5, cls: "notable", mood: "shout" }, (c, o, t) => {
    puff(c, o, t, 0.05, 1.2, { f: 1500, q: 0.9 });
    voice(c, o, t, 0.32, { v: "a", v2: "e", f0: [225, 258], gain: 0.65, rough: 0.35, grit: 4 });
    return 0.45;
  });
  def("raise", "Price goes UP (he raised it)", { prio: 2, gap: 1, cls: "notable", mood: "annoyed" }, (c, o, t) => {
    puff(c, o, t, 0.14, 1.3, { f: 900, q: 1.1, att: 0.012 });
    voice(c, o, t + 0.01, 0.16, { v: "o", f0: [110, 80], gain: 0.5, rough: 0.5 });
    const w = tone(c, null, "sine", 330, 1320, t + 0.2, 0.36, { vib: 16, vibHz: 11 }), e = env(c, t + 0.2, 0.36, 0.3, 0.02, 0.08);
    w.connect(e); e.connect(o);
    bell(c, o, t + 0.56, 1760, { decay: 0.4, parts: [1, 2.4], amps: [1, 0.3], gain: 0.2 });
    return 0.95;
  });
  def("deal", "Cha-ching! (a deal)", { prio: 2, gap: 1.6, cls: "register", mood: "pleased" }, (c, o, t) => { register(c, o, t, false); return 1.1; });
  def("dealBig", "Big cha-ching (a deal over 22% off)", { prio: 2, gap: 2.5, cls: "notable", mood: "sobbing" }, (c, o, t) => { register(c, o, t, true); return 1.7; });
  def("tada", "Ta-da! (someone filled the whole bag)", { prio: 2, gap: 8, cls: "notable", mood: "pleased" }, (c, o, t) => {
    brass(c, o, t, 523, 0.12, { gain: 0.26, c1: 2800, c2: 2200 });
    [784, 1047].forEach((f) => brass(c, o, t + 0.16, f, 0.55, { gain: 0.2, c1: 2800, c2: 1800, vib: 3 }));
    bell(c, o, t + 0.16, 2093, { decay: 0.8, gain: 0.16 });
    return 0.9;
  });
  def("rush", "Festive rush jingle", { prio: 3, gap: 5, mood: "pleased" }, (c, o, t) => {
    [523, 587, 659, 784, 659, 784, 880, 1047].forEach((f, i) => mallet(c, o, t + i * 0.125, f, 0.4));
    for (let i = 0; i < 4; i++) click(c, o, t + i * 0.25, 4200, 0.12, 2);
    [1047, 1319, 1568].forEach((f) => mallet(c, o, t + 1.05, f, 0.3, 0.6));
    return 1.7;
  });
  def("tight", "Month-end squeeze sting", { prio: 3, gap: 5, mood: "annoyed" }, (c, o, t) => {
    const lo = { gain: 0.3, c0: 250, c1: 700, c2: 350, att: 0.03 };
    brass(c, o, t, 110, 0.26, lo); brass(c, o, t + 0.32, 110, 0.26, lo); brass(c, o, t + 0.64, 98, 0.9, { ...lo, droop: 0.85 });
    [0, 0.32, 0.64].forEach((d) => { const n = tone(c, null, "sine", 90, 45, t + d, 0.18), e = perc(c, t + d, 0.18, 0.6, 0.003); n.connect(e); e.connect(o); });
    return 1.7;
  });
  def("bell", "Bell (one minute left)", { prio: 3, gap: 5 }, (c, o, t) => {
    bell(c, o, t, 1760, { decay: 0.6, gain: 0.3 }); bell(c, o, t + 0.22, 1760, { decay: 0.9, gain: 0.3 });
    return 1.2;
  });
  def("fanfare", "Podium fanfare", { prio: 3, gap: 2, mood: "pleased" }, (c, o, t) => {
    [[523, 0], [659, 0.15], [784, 0.3]].forEach(([f, d]) => brass(c, o, t + d, f, 0.17, { gain: 0.26, c1: 3200, c2: 2400 }));
    [523, 659, 784, 1047].forEach((f) => brass(c, o, t + 0.46, f, 0.95, { gain: 0.14, c1: 3200, c2: 2000, vib: 3 }));
    bell(c, o, t + 0.46, 2093, { decay: 1.2, gain: 0.18 }); bell(c, o, t + 0.56, 3136, { decay: 1.0, gain: 0.14 });
    return 1.7;
  });
  def("close", "Closing bell and shutters down", { prio: 3, gap: 2 }, (c, o, t) => {
    for (let i = 0; i < 3; i++) bell(c, o, t + i * 0.2, 1568, { decay: 0.8, gain: 0.3 });
    shutter(c, o, t + 0.65, 0.55, true);
    return 1.6;
  });
  def("pop", "Sound on", { prio: 3, gap: 0 }, (c, o, t) => {
    const n = tone(c, null, "sine", 620, 1000, t, 0.08), e = env(c, t, 0.08, 0.25, 0.005, 0.04);
    n.connect(e); e.connect(o);
    return 0.12;
  });

  // ---------------------------------------------------------------- recorded sounds (optional)
  // static/sfx/bazaar-sfx.json describes one audio sprite (bazaar-sfx.mp3) that holds several recorded variants of a sound:
  //   { "file": "bazaar-sfx.mp3", "offset": 0, "clips": { "hmm": [{ "t": 1.2, "d": 0.6, "id": "...", "gain": 1 }, ...], ... } }
  // t and d are seconds into the file, gain (optional, linear) levels the variants of one sound against each other. One request per
  // player; decoded once. A sound with recordings plays one of them (never the
  // same one twice in a row) instead of its synthesised version; a missing sprite or a failed decode leaves the synthesised sounds.
  const SPRITE_URL = "/static/sfx/bazaar-sfx.json";
  // Output level of the recorded version of each sound, trimming the loudness-matched clips against each other and against the
  // synthesised sounds (set with tools/sfx_check.py --tune).
  const CAL_REC = {
    door: 0.259, open: 0.456, hmm: 0.274, tsk: 0.314, hmph: 0.338, heh: 0.288, laugh: 0.356, wail: 0.321, shout: 0.455, raise: 0.458,
    deal: 0.320, dealBig: 0.418, tada: 0.355, rush: 0.463, tight: 0.446, bell: 0.375, fanfare: 0.405, close: 0.372, pop: 0.362,
  };
  const sprite = { buf: null, offset: 0, state: "none", pick: {} };         // state: none | loading | ready | failed
  const recorded = (d) => !!(sprite.buf && d.rec && d.rec.length);

  function useSprite(meta, buf) {
    sprite.buf = buf;
    sprite.offset = Number(meta.offset) || 0;
    for (const d of Object.values(SOUNDS)) {
      const list = (meta.clips && meta.clips[d.name]) || [];
      d.rec = list.filter((k) => k && k.d > 0.03 && k.t >= 0 && k.t + k.d <= buf.duration + 0.05);
    }
    sprite.state = "ready";
  }
  async function decodeSprite(bytes, meta) {
    const c = ctx || new OAC(1, 1, 44100);                                   // any context can decode; the buffer plays in any other
    useSprite(meta, await c.decodeAudioData(bytes));
  }
  async function loadSprite(url) {
    if (sprite.state === "loading" || sprite.state === "ready") return sprite.state;
    sprite.state = "loading";
    try {
      const base = new URL(url || SPRITE_URL, location.href);
      const m = await fetch(base);
      if (!m.ok) throw new Error("HTTP " + m.status);
      const meta = await m.json();
      const f = await fetch(new URL(meta.file, base));
      if (!f.ok) throw new Error("HTTP " + f.status);
      await decodeSprite(await f.arrayBuffer(), meta);
    } catch (e) { sprite.state = "failed"; stats.spriteError = String(e); }
    return sprite.state;
  }
  function variant(d, want) {
    const n = d.rec.length;
    if (want !== undefined) return want % n;
    let i = Math.floor(Math.random() * n);
    if (n > 1 && i === sprite.pick[d.name]) i = (i + 1) % n;
    return (sprite.pick[d.name] = i);
  }
  // Schedules one recording at t, with short fades so a cut never clicks. Returns its length in seconds.
  function clip(c, dest, t, d, want) {
    const k = d.rec[variant(d, want)], at = k.t + sprite.offset, len = Math.max(0.05, Math.min(k.d, sprite.buf.duration - at));
    const fade = Math.min(0.025, len / 4), s = c.createBufferSource(), g = c.createGain(), top = Number(k.gain) > 0 ? Number(k.gain) : 1;
    s.buffer = sprite.buf;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(top, t + Math.min(0.006, len / 4));
    g.gain.setValueAtTime(top, t + len - fade);
    g.gain.linearRampToValueAtTime(0.0001, t + len);
    s.connect(g); g.connect(dest);
    s.start(t, at, len);
    return len;
  }
  const levelOf = (d, rec) => (rec ? CAL_REC[d.name] ?? 1 : d.g);

  // ---------------------------------------------------------------- output chain, state and the public API
  function chain(c, vol, limiter) {
    const input = c.createGain(), master = c.createGain();
    master.gain.value = vol;
    if (limiter === false) input.connect(master);
    else {
      const comp = c.createDynamicsCompressor();
      comp.threshold.value = -16; comp.knee.value = 14; comp.ratio.value = 5; comp.attack.value = 0.004; comp.release.value = 0.18;
      input.connect(comp); comp.connect(master);
    }
    master.connect(c.destination);
    return { input, master };
  }

  let ctx = null, out = null, level = "on", role = "player", key = "bz_sfx", primed = false, tok = 0;
  const stats = { played: {}, real: {}, skipped: 0, dropped: 0, errors: 0, lastError: "", spriteError: "" };
  const last = {}, hist = {}, listeners = [];
  let ring = [], lastAt = -9;
  // Most sounds a busy host screen makes per rolling minute, by kind: his routine voice, the cash register, and the rarer funny ones.
  const BUDGET = { voice: 5, register: 7, notable: 7 };

  const ls = {
    get() { try { return window.localStorage.getItem(key) || ""; } catch (e) { return ""; } },
    set(v) { try { window.localStorage.setItem(key, v); } catch (e) { /* private mode */ } },
  };
  const state = () => (level === "off" ? "off" : ctx && ctx.state === "running" ? level : "locked");
  const notify = () => listeners.forEach((f) => { try { f(); } catch (e) { /* ignore */ } });

  function unlock() {
    if (!AC || level === "off") return;
    try {
      if (!ctx) {
        ctx = new AC({ latencyHint: "interactive" });
        out = chain(ctx, LEVELS[level], true);
        ctx.onstatechange = notify;
      }
      if (ctx.state !== "running") { const p = ctx.resume(); if (p && p.catch) p.catch(() => {}); }
      if (!primed) {                                     // iOS wants one sound started inside a tap
        primed = true;
        const s = ctx.createBufferSource();
        s.buffer = ctx.createBuffer(1, 1, 22050); s.connect(ctx.destination); s.start(0);
      }
      notify();
    } catch (e) { /* sound is optional */ }
  }
  for (const ev of ["pointerdown", "touchend", "click", "keydown"]) {
    document.addEventListener(ev, (e) => { if (!(e.target && e.target.closest && e.target.closest("[data-sfx]"))) unlock(); }, { capture: true, passive: true });
  }

  function setLevel(name) {
    if (LEVELS[name] === undefined) return;
    level = name;
    ls.set(name);
    if (name === "off") { if (out) out.master.gain.value = 0; }
    else { unlock(); loadSprite(); if (out) out.master.gain.setTargetAtTime(LEVELS[name], ctx.currentTime, 0.02); }
    notify();
  }
  function setup(o = {}) {
    role = o.role || role; key = o.key || key;
    const stored = ls.get();
    level = LEVELS[stored] !== undefined ? stored : LEVELS[o.def] !== undefined ? o.def : "on";
    if (out) out.master.gain.value = LEVELS[level];
    if (level !== "off" && o.sprite !== false) loadSprite(typeof o.sprite === "string" ? o.sprite : undefined);
    notify();
  }

  function admit(name, d, now) {
    if (d.prio >= 3) return true;
    if (now - (last[name] ?? -9) < d.gap) return false;
    ring = ring.filter((e) => e > now);
    if (d.prio === 1 && (ring.length >= 2 || now - lastAt < 0.4)) return false;
    if (d.prio === 2 && ring.length >= 3) return false;
    if (role === "host" && d.cls) {                      // on the shared screen a busy shop must not turn into noise
      const h = (hist[d.cls] = (hist[d.cls] || []).filter((s) => s > now - 60));
      if (h.length >= BUDGET[d.cls]) return false;
    }
    return true;
  }

  // Play one sound. Returns its length in seconds, or 0 when it was not played (locked, off, hidden tab, or too busy).
  function play(name, o = {}) {
    try {
      const d = SOUNDS[name];
      if (!d) return 0;
      if (level === "off" || state() !== level) { stats.dropped++; return 0; }
      if (document.hidden && role !== "host" && !o.force) { stats.dropped++; return 0; }
      const now = ctx.currentTime;
      if (!o.force && !admit(name, d, now)) { stats.skipped++; return 0; }
      const bus = ctx.createGain(), rec = recorded(d);
      bus.gain.value = levelOf(d, rec) * (o.gain ?? 1);
      bus.connect(out.input);
      const secs = (rec ? clip(ctx, bus, now + 0.02, d) : d.fn(ctx, bus, now + 0.02)) || 1;
      last[name] = now; lastAt = now; ring.push(now + secs);
      if (d.cls) (hist[d.cls] = hist[d.cls] || []).push(now);
      stats.played[name] = (stats.played[name] || 0) + 1;
      if (rec) stats.real[name] = (stats.real[name] || 0) + 1;
      return secs;
    } catch (e) { stats.errors++; stats.lastError = String(e); return 0; }
  }

  // Raju Anna's voice for a line, chosen by the mood on his face. Routine moods are voiced only some of the time.
  const VOICE = { thinking: ["hmm", 0.45], unimpressed: ["tsk", 0.6], annoyed: ["hmph", 1], smirk: ["heh", 1], pleased: ["laugh", 0.85], sobbing: ["wail", 1], shout: ["shout", 1] };
  function line(kind, mood, o = {}) {
    if (kind === "RAISE") return play("raise", o);
    const v = VOICE[mood];
    if (!v) return 0;
    if (!o.always && !o.force && Math.random() > v[1]) { stats.skipped++; return 0; }
    return play(v[0], o);
  }
  // A shopper's own reply (haggle, buy or walk): always voiced; a deal rings the register first.
  function reply(r) {
    if (!r) return;
    if (r.deal) {
      play((r.deal.discount_pct || 0) >= 22 ? "dealBig" : "deal", { force: true });
      setTimeout(() => line(r.kind, r.mood, { always: true }), 650);
    } else line(r.kind, r.mood, { always: true });
  }

  // Runs fn once the audio is running (the first tap can take a moment to wake it up).
  function whenReady(fn) {
    if (level === "off") return;
    unlock();
    if (!ctx) return;
    if (ctx.state === "running") { fn(); return; }
    try {
      const p = ctx.resume();
      if (p && p.then) p.then(() => { if (ctx.state === "running") fn(); }).catch(() => {});
    } catch (e) { /* ignore */ }
  }

  // Tap-to-change button: names is the order it cycles through (for example ["on", "soft", "off"]).
  function bind(btn, names, paint) {
    if (!btn) return;
    if (!AC) { btn.classList.add("hidden"); return; }                          // no Web Audio in this browser: no button either
    btn.setAttribute("data-sfx", "1");
    let shown = "";
    const draw = () => {
      const st = state();
      if (st === shown) return;                                                // only touch the page when something changed
      shown = st;
      paint(btn, st);
      btn.classList.toggle("locked", st === "locked");
    };
    btn.addEventListener("click", () => {
      if (state() === "locked") { whenReady(() => play("pop", { force: true })); return; }      // the first tap only wakes the audio
      setLevel(names[(names.indexOf(level) + 1) % names.length]);
      whenReady(() => play("pop", { force: true }));
    });
    listeners.push(draw);
    draw();
  }

  // Plays every sound once with its name (for the host's sound check). Resolves when finished or stopped.
  function demo(onStep) {
    const me = ++tok, names = Object.keys(SOUNDS).filter((n) => n !== "pop");
    return new Promise((done) => {
      let i = 0;
      const next = () => {
        if (me !== tok || i >= names.length) { done(me === tok); return; }
        const n = names[i++], secs = play(n, { force: true }) || 1;
        if (onStep) onStep({ name: n, label: SOUNDS[n].label, mood: SOUNDS[n].mood, i, n: names.length });
        setTimeout(next, secs * 1000 + 600);
      };
      whenReady(next);
      setTimeout(() => { if (me === tok && i === 0) done(false); }, 3000);       // audio never woke up: give up quietly
    });
  }

  // Renders cues [{t, sound, gain, variant, synth}] to samples without playing them (used by tests and tools/sfx_check.py).
  // `variant` picks which recording of a sound (default the first); `synth: true` forces the synthesised version.
  // Returns { data: Float32Array (mono), ends: when each cue stops ringing, in seconds }.
  async function render(cues, duration, o = {}) {
    const rate = o.rate || 44100, c = new OAC(1, Math.ceil(duration * rate), rate), ch = chain(c, o.vol ?? LEVELS.on, o.limiter);
    const ends = [];
    for (const q of cues) {
      const d = SOUNDS[q.sound];
      if (!d) { ends.push(q.t); continue; }
      const rec = recorded(d) && !q.synth, bus = c.createGain();
      bus.gain.value = levelOf(d, rec) * (q.gain ?? 1);
      bus.connect(ch.input);
      ends.push(q.t + ((rec ? clip(c, bus, q.t, d, q.variant ?? 0) : d.fn(c, bus, q.t)) || 0));
    }
    return { data: (await c.startRendering()).getChannelData(0), ends };
  }

  window.Sfx = {
    setup, unlock, play, line, reply, bind, demo, render, stats,
    stopDemo: () => { tok++; },
    tune: (map) => { for (const [n, g] of Object.entries(map)) { const d = SOUNDS[n]; if (d) { if (recorded(d)) CAL_REC[n] = g; else d.g = g; } } },     // for tools/sfx_check.py --tune
    state, level: () => level, set: setLevel,
    names: () => Object.values(SOUNDS).map((d) => ({ name: d.name, label: d.label, mood: d.mood, prio: d.prio, g: levelOf(d, recorded(d)), real: recorded(d), variants: (d.rec || []).length })),
    sprite: () => sprite.state, loadSprite, loadSpriteData: decodeSprite,
    onChange: (f) => listeners.push(f),
  };
})();
