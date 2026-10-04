# Hero film: "One number, traced"

`one-number-traced.mp4` is a 64-second narrated film, 1080p30, with English subtitles in
`one-number-traced.srt`. It follows one answer from the question to the transactions
behind it, then shows the verifier, the refusals, and the evaluation result.

Everything on screen comes from the repository's recorded run `eval/runs/2026-10-02-flash-lite`:

| On screen | Source |
|---|---|
| 13,142,986.71 UNI sent to the Uniswap Foundation custody multisig | q021 (`full` config). The verifier matched `c2:counterparties[2].amounts[0].amount` |
| Two transactions: 2,457,002 and 10,685,984.71 UNI | `0x9188543c…df812947d42` and `0xd8304a66…a5284076b66b0e` |
| 925,034,000,000,000,000,000,000 UNI | The naive baseline (a model reading raw transactions), asked for 2024 UNI outflows |
| The nine answer tiles | Recorded answers, refusals and abstentions from the same run |
| 88.7% vs 6.5% | `metrics.json`: answerable questions fully correct, full system vs naive baseline |

## How it is made

The film is built with [onetake](https://github.com/feitangyuan/onetake). It is one HTML
composition (`comp.html`) in which every value is a pure function of time. Onetake renders
it frame by frame with shutter motion blur and synthesises the sound effects. Onetake's
probe gave this cut a continuity score of 1.00: every section boundary is carried by an
object that moves.

- `comp.html` holds the composition: the timeline, the camera, `__track`, `__motion` and `__events`.
- `look.json` sets the palette and faces. Onetake's `look.py apply` turns it into `look.js`,
  with fonts subset and inlined.
- `vo_lines.json` and `tts.py` produce the narration with Gemini TTS
  (`gemini-2.5-flash-preview-tts`, voice "Charon").
- `dump_events.py` and `score.py` build the score. Sound effects come from onetake's
  palette, placed at the composition's own events. The voice track is laid at the
  composition's VO times, and the mix is mastered to about −16 LUFS.

Onetake is licensed under PolyForm Noncommercial 1.0.0, so its library (`lib/motion.js`) and
scripts are **not** included here. To rebuild:

```bash
git clone https://github.com/feitangyuan/onetake /tmp/onetake
cp /tmp/onetake/lib/motion.js docs/video/film/
cd docs/video/film
python /tmp/onetake/scripts/look.py apply look.json comp.html        # writes look.js
GEMINI_API_KEY=... python tts.py                                      # vo/l1..l8.wav
# trim leading/trailing silence and resample to 48 kHz into vot/ (ffmpeg silenceremove)
python dump_events.py comp.html                                       # events.json
python score.py /tmp/onetake/scripts                                  # score_raw.wav
ffmpeg -i score_raw.wav -af loudnorm=I=-16:TP=-3.5:LRA=11 -ar 48000 score.wav
python /tmp/onetake/scripts/render.py comp.html --out one-number-traced.mp4 --sfx score.wav
```

Preview in a browser with `comp.html?play`, or pin a frame with `comp.html?t=28.4&hud`.
The 7-minute walkthrough one folder up is the deep dive.
