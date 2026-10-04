"""Builds docs/video/dao-treasury-analyst.mp4 from scenes.py.

Steps: render each slide with headless Chromium, synthesize each narration with Gemini TTS
(cached by text hash), then assemble with ffmpeg (fades, AAC audio, soft subtitles).

Usage: GEMINI_API_KEY=... uv run python docs/video/build.py
Needs: ffmpeg, a Chromium binary (CHROMIUM env var or the Playwright default path).
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import subprocess
import time
from pathlib import Path

import httpx
from scenes import SCENES, Scene

HERE = Path(__file__).parent
WORK = HERE / "build"
OUT = HERE / "dao-treasury-analyst.mp4"
SRT = HERE / "dao-treasury-analyst.srt"
CHROMIUM = os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
TTS_MODEL = os.environ.get("TTS_MODEL", "gemini-3.8-flash-tts")
# Used when the primary model's free-tier daily quota (10 requests) is exhausted.
TTS_FALLBACK = os.environ.get("TTS_FALLBACK_MODEL", "gemini-3.1-flash-tts-preview")
VOICE = os.environ.get("TTS_VOICE", "Charon")
PAD = 0.6  # seconds of silence before and after each narration
FADE = 0.4

CSS = """
:root{--bg:#0b1020;--panel:#121a30;--line:#24304f;--text:#e6ebf5;--muted:#93a0bd;
--accent:#7aa2ff;--good:#56d39a;--bad:#ff7b72;--pink:#d2a8ff}
*{box-sizing:border-box}
html{background:#0b1020}
body{position:relative;margin:0;width:1920px;height:1080px;background:radial-gradient(1200px 700px at 80% -10%,#1b2a55 0%,var(--bg) 60%);
color:var(--text);font-family:Inter,"Segoe UI",Helvetica,Arial,sans-serif;padding:90px 120px;overflow:hidden}
h1.big{font-size:104px;margin:10px 0 24px;letter-spacing:-2px}
h2{font-size:64px;margin:0 0 40px;letter-spacing:-1px}
.lead{font-size:38px;line-height:1.45;color:var(--text);margin:0 0 36px}
.kicker{font-size:28px;color:var(--accent);text-transform:uppercase;letter-spacing:4px}
.center{height:100%;display:flex;flex-direction:column;justify-content:center;align-items:flex-start}
.pill{display:inline-block;margin-top:30px;padding:16px 30px;border:2px solid var(--accent);
border-radius:999px;font-size:32px;color:var(--accent)}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:50px;align-items:start}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:36px;margin-bottom:46px}
.card{background:var(--panel);border:2px solid var(--line);border-radius:22px;padding:38px}
.card.bad{border-color:var(--bad)} .card.good{border-color:var(--good)}
.label{font-size:26px;color:var(--muted);margin-bottom:14px;text-transform:uppercase;letter-spacing:2px}
.num{font-size:52px;font-weight:700;margin-bottom:10px;word-break:break-word}
.card.bad .num{color:var(--bad)} .card.good .num{color:var(--good)}
.small{font-size:28px;color:var(--muted);line-height:1.4}
.list{font-size:34px;line-height:1.6;margin:0;padding-left:40px}
.list li{margin-bottom:12px}
.foot{position:absolute;bottom:60px;left:120px;font-size:24px;color:var(--muted)}
.flow{display:flex;align-items:center;gap:26px;margin:70px 0}
.box{background:var(--panel);border:2px solid var(--line);border-radius:20px;padding:34px 36px;
font-size:38px;font-weight:600;text-align:center;min-width:300px}
.box span{display:block;font-size:28px;font-weight:400;color:var(--muted);margin-top:10px}
.box.hl{border-color:var(--accent)}
.arrow{font-size:52px;color:var(--accent)}
.term{background:#0d1117;border:2px solid #30363d;border-radius:18px;padding:44px 50px;
font-family:"DejaVu Sans Mono",Menlo,Consolas,monospace;font-size:27px;line-height:1.55;color:#c9d1d9}
.term div{margin-bottom:10px} .term pre{white-space:pre-wrap;margin:22px 0;font:inherit}
.g{color:#7ee787} .m{color:#8b949e} .p{color:var(--pink)}
.code pre{background:#0d1117;border:2px solid #30363d;border-radius:18px;padding:36px;margin:0;
font-family:"DejaVu Sans Mono",Menlo,monospace;font-size:28px;line-height:1.5;color:#c9d1d9}
.ok{margin-top:20px;font-size:28px;color:var(--good);font-family:"DejaVu Sans Mono",monospace}
.qa{background:var(--panel);border:2px solid var(--line);border-radius:18px;padding:26px 34px;margin-bottom:24px}
.q{font-size:32px;font-weight:600;margin-bottom:10px} .a{font-size:28px;color:var(--good);line-height:1.4}
table{border-collapse:collapse;font-size:32px;width:100%}
th,td{padding:16px 22px;border-bottom:2px solid var(--line);text-align:right}
th:first-child,td:first-child{text-align:left;color:var(--muted)}
th{color:var(--accent);font-weight:600} td.good{color:var(--good);font-weight:700} td.bad{color:var(--bad)}
"""


def render_slide(scene: Scene, path: Path) -> None:
    page = WORK / f"{scene.id}.html"
    page.write_text(
        f"<!doctype html><meta charset='utf-8'><style>{CSS}</style><body>{scene.html}</body>"
    )
    subprocess.run(
        [
            CHROMIUM,
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--hide-scrollbars",
            f"--screenshot={path}",
            "--window-size=1920,1240",
            f"file://{page}",
        ],
        check=True,
        capture_output=True,
    )


def _synthesize(model: str, text: str) -> bytes | None:
    """Returns audio bytes, or None if the model's daily quota is exhausted."""
    body = {
        "contents": [
            {
                "parts": [
                    {
                        "text": "Read this in a calm, clear, professional tone, "
                        f"at a natural pace:\n\n{text}"
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE}}},
        },
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    for attempt in range(4):
        r = httpx.post(
            url, json=body, timeout=180, headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]}
        )
        if r.status_code == 200:
            part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
            return base64.b64decode(part["data"])
        if r.status_code == 429 and "PerDay" in r.text:
            return None
        time.sleep(10 * (attempt + 1))
    r.raise_for_status()
    return None


def tts(scene: Scene, path: Path) -> None:
    for model in (TTS_MODEL, TTS_FALLBACK):
        key = hashlib.sha256(f"{model}|{VOICE}|{scene.narration}".encode()).hexdigest()[:16]
        cached = WORK / f"tts-{key}.wav"
        if not cached.exists():
            raw = _synthesize(model, scene.narration)
            if raw is None:
                print(f"  {model}: daily quota exhausted, trying fallback")
                continue
            if raw[:4] == b"RIFF":
                cached.write_bytes(raw)
            else:  # raw 16-bit PCM at 24 kHz
                pcm = WORK / f"tts-{key}.pcm"
                pcm.write_bytes(raw)
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-v",
                        "error",
                        "-f",
                        "s16le",
                        "-ar",
                        "24000",
                        "-ac",
                        "1",
                        "-i",
                        str(pcm),
                        str(cached),
                    ],
                    check=True,
                )
        path.write_bytes(cached.read_bytes())
        (WORK / f"{scene.id}.voice").write_text(model)
        return
    raise RuntimeError(f"no TTS model available for {scene.id}")


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def segment(png: Path, wav: Path, out: Path) -> float:
    total = duration(wav) + 2 * PAD
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-loop",
            "1",
            "-framerate",
            "30",
            "-i",
            str(png),
            "-i",
            str(wav),
            "-filter_complex",
            # Slides are rendered taller than 1080 px (Chromium's viewport is shorter than its
            # window); the slide itself is the top 1920x1080.
            f"[0:v]crop=1920:1080:0:0,format=yuv420p,fade=t=in:st=0:d={FADE},"
            f"fade=t=out:st={total - FADE:.3f}:d={FADE}[v];"
            f"[1:a]adelay={int(PAD * 1000)}|{int(PAD * 1000)},apad,atrim=0:{total:.3f},"
            f"aformat=sample_rates=48000:channel_layouts=stereo[a]",
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-t",
            f"{total:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-tune",
            "stillimage",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(out),
        ],
        check=True,
    )
    return total


def srt_time(t: float) -> str:
    ms = round(t * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def subtitles(scenes: list[Scene], spans: list[tuple[float, float]]) -> str:
    """One cue per sentence, timed proportionally to its length within the narration."""
    cues, n = [], 1
    for scene, (start, speech) in zip(scenes, spans, strict=True):
        sentences = [s for s in re.split(r"(?<=[.?!])\s+", scene.narration) if s]
        chars = sum(len(s) for s in sentences)
        t = start
        for s in sentences:
            d = speech * len(s) / chars
            cues.append(f"{n}\n{srt_time(t)} --> {srt_time(t + d)}\n{html.unescape(s)}\n")
            n, t = n + 1, t + d
    return "\n".join(cues)


def main() -> None:
    WORK.mkdir(exist_ok=True)
    parts, spans, clock = [], [], 0.0
    for scene in SCENES:
        png, wav, mp4 = (WORK / f"{scene.id}.{ext}" for ext in ("png", "wav", "mp4"))
        render_slide(scene, png)
        tts(scene, wav)
        total = segment(png, wav, mp4)
        spans.append((clock + PAD, duration(wav)))
        clock += total
        parts.append(mp4)
        print(f"{scene.id}: {total:.1f}s")
    listing = WORK / "concat.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in parts))
    SRT.write_text(subtitles(SCENES, spans))
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-i",
            str(SRT),
            "-map",
            "0",
            "-map",
            "1",
            "-c",
            "copy",
            "-c:s",
            "mov_text",
            "-metadata:s:s:0",
            "language=eng",
            "-movflags",
            "+faststart",
            str(OUT),
        ],
        check=True,
    )
    print(f"wrote {OUT} ({clock:.0f}s, {OUT.stat().st_size / 1e6:.1f} MB) and {SRT}")


if __name__ == "__main__":
    main()
