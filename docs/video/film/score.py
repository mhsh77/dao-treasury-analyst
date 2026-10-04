"""Score for 'One number, traced': onetake's palette placed at the comp's own events, plus the VO."""

import json
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, sys.argv[1])
from sfx_palette import SR, Score, air, bubble, glass, hp, lp, sub, wood

ev = json.loads(Path("events.json").read_text())
DUR = ev["T"]
VO = [0.6, 4.9, 12.3, 18.5, 25.6, 35.8, 45.4, 56.0]
s = Score(dur=DUR, T60=1.3)
rng = np.random.default_rng(3)


def P(e):
    return 0.6 * e["pan"]


word_notes = [523.3, 587.3, 659.3, 784.0]
n_word = n_tick = n_light = 0
for e in ev["events"]:
    t, k, v, p = e["t"], e["kind"], e["v"], P(e)
    if k == "word":
        s.place(glass(word_notes[n_word], 0.7, 0.5), t, 0.10 * v, p, send=0.5)
        n_word += 1
    elif k == "morph":
        s.place(air(0.55, 300, 2200, 1.2, 0.55), t - 0.1, 0.22, p, send=0.45)
    elif k == "type":
        n = int(len("How much UNI did the treasury send to the Uniswap Foundation?") / 38 / 0.11)
        for i in range(n):
            if rng.random() < 0.6:
                s.place(
                    wood(rng.uniform(1400, 2100), 0.05),
                    t + i * 0.11 + rng.uniform(0, 0.03),
                    rng.uniform(0.05, 0.09),
                    -0.1,
                    send=0.12,
                )
    elif k == "click":
        s.place(wood(900, 0.08), t - 0.06, 0.22, p, send=0.15)
        s.place(wood(1300, 0.06), t + 0.02, 0.16, p, send=0.15)
    elif k == "pop":
        s.place(bubble(480, 0.2), t, 0.16 * v, p, send=0.3)
    elif k == "tick":
        s.place(glass([880, 988, 1175][n_tick], 0.8, 0.7), t, 0.14, p, send=0.45)
        n_tick += 1
    elif k == "land":
        s.place(sub(58, 0.9), t + 0.05, 0.55, 0, send=0.3)
        s.place(glass(1318.5, 1.4, 0.4), t + 0.06, 0.08, 0, send=0.7)
    elif k == "dive":
        s.place(air(0.75, 200, 3500, 1.4, 0.85), t, 0.32, 0, send=0.45)
    elif k == "split":
        s.place(sub(70, 0.5), t, 0.4, 0, send=0.3)
        s.place(wood(420, 0.1), t, 0.2, 0, send=0.25)
    elif k == "drop":
        s.place(bubble(300, 0.22), t + 0.6, 0.14 * v, p, send=0.3)
    elif k == "gather":
        s.place(air(0.9, 2400, 300, 1.2, 0.7), t, 0.24, p, send=0.5)
    elif k == "stamp":
        s.place(sub(66, 0.6), t, 0.5, p, send=0.3)
        s.place(wood(260, 0.12), t, 0.35, p, send=0.25)
        s.place(glass(1046.5, 1.2, 0.6), t + 0.04, 0.09, p, send=0.6)
        s.place(glass(1568, 1.2, 0.5), t + 0.08, 0.06, p, send=0.6)
    elif k == "whip":
        s.place(
            air(0.42, 400, 4200, 1.0, 0.6),
            t - 0.05,
            0.36,
            -0.5 if t < 31 else 0.5,
            send=0.35,
            pan_to=0.5 if t < 31 else -0.5,
        )
    elif k == "slam":
        s.place(sub(48, 1.0), t, 0.6, 0, send=0.35)
    elif k == "xstamp":
        s.place(sub(44, 0.7), t, 0.55, p, send=0.3)
        s.place(wood(190, 0.14), t, 0.4, p, send=0.25)
        s.place(glass(233, 0.9, 1.2), t + 0.02, 0.10, p, send=0.4)
    elif k == "fall":
        s.place(air(0.45, 1800, 250, 1.2, 0.3), t, 0.25, p, send=0.4)
    elif k == "pull":
        s.place(air(1.9, 1600, 220, 1.0, 0.35), t, 0.28, 0, send=0.6)
    elif k == "light":
        s.place(glass([587.3, 523.3, 440.0][n_light], 1.0, 0.8), t, 0.13, p, send=0.55)
        n_light += 1
    elif k == "grow":
        s.place(air(1.0, 250, 2800, 1.3, 0.9), t, 0.2 * v, p, send=0.4)
        s.place(glass(783.99 if v > 0.9 else 392.0, 1.6, 0.6), t + 0.85, 0.12 * v, p, send=0.6)
    elif k == "hit":
        s.place(sub(56, 0.32), t, 0.62, 0, send=0.2)
        s.place(wood(300, 0.08), t, 0.3, 0, send=0.15)
    elif k == "mark":
        s.place(sub(41, 2.2), t, 0.55, 0, send=0.5)
        for f, d in ((261.6, 0), (392.0, 0.05), (587.3, 0.1)):
            s.place(glass(f, 2.6, 0.35), t + 0.25 + d, 0.07, 0, send=0.8)

# a low bed: two detuned partials, filtered noise breath, silent in the dramatic beats
n = int(SR * DUR)
tt = np.arange(n) / SR
bed = 0.5 * np.sin(2 * np.pi * 55 * tt) + 0.35 * np.sin(
    2 * np.pi * 82.6 * tt + 0.4 * np.sin(2 * np.pi * 0.13 * tt)
)
bed += 0.35 * lp(hp(np.random.default_rng(5).standard_normal(n), 120), 600)
env = np.interp(
    tt,
    [0, 2, 17.5, 18.2, 30.4, 30.6, 33.5, 35, 54.8, 55.0, 56.3, 60, DUR],
    [0, 0.6, 0.7, 0.25, 0.7, 0, 0, 0.65, 0.8, 0, 0.7, 0.55, 0],
)
fx = s.mix(peak_db=-8.0)
bed = (bed * env)[:, None] * np.array([[1, 1]]) * 10 ** (-30 / 20)
mix = fx[:n] + bed[: len(fx)]

# VO, centred, with the effects ducked 5 dB under it
vo = np.zeros(n)
duck = np.ones(n)
for i, t0 in enumerate(VO):
    with wave.open(f"vot/l{i + 1}.wav") as w:
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16) / 32767
    a = int(t0 * SR)
    vo[a : a + len(x)] += x[: n - a]
    duck[a : a + len(x)] = 10 ** (-5 / 20)
k = int(0.12 * SR)
duck = np.convolve(duck, np.ones(k) / k, "same")
vo = vo / np.abs(vo).max() * 10 ** (-3 / 20)
out = mix * duck[:, None] * 10 ** (-5 / 20) + vo[:, None] * 0.75
out = out / np.abs(out).max() * 0.89
with wave.open("score_raw.wav", "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes((out * 32767).astype(np.int16).tobytes())
print("score_raw.wav", DUR, "s")
