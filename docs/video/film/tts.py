"""Narration for the hero film: one Gemini TTS request per line of vo_lines.json (voice "Charon")."""

import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

MODEL = sys.argv[1] if len(sys.argv) > 1 else "gemini-2.5-flash-preview-tts"
lines = json.loads(Path("vo_lines.json").read_text())
for i, text in enumerate(lines):
    out = f"vo/l{i + 1}.wav"
    if os.path.exists(out):
        continue
    body = {
        "contents": [
            {
                "parts": [
                    {
                        "text": "Read this as the narrator of a polished product film: warm, confident, unhurried, clear:\n\n"
                        + text
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Charon"}}},
        },
    }
    r = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
        json=body,
        timeout=180,
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
    )
    if r.status_code != 200:
        print(i + 1, r.status_code, r.text[:200])
        break
    raw = base64.b64decode(r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
    if raw[:4] == b"RIFF":
        Path(out).write_bytes(raw)
    else:
        Path(out + ".pcm").write_bytes(raw)
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "s16le",
                "-ar",
                "24000",
                "-ac",
                "1",
                "-i",
                out + ".pcm",
                out,
            ],
            check=True,
        )
    d = float(
        subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out],
            capture_output=True,
            text=True,
        ).stdout
    )
    print(f"l{i + 1}: {d:.2f}s  {len(text) / d:.1f} c/s")
    time.sleep(25)
