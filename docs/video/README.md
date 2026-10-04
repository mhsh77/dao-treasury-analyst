# Project video

The 60-second hero film lives in [`film/`](film/). This folder holds the 7-minute deep dive.

`dao-treasury-analyst.mp4` (about 7 minutes, 1080p, narrated, with a soft English subtitle
track; the same subtitles are in `dao-treasury-analyst.srt`).

Everything on screen comes from the repository: the answers are recorded eval outputs
(`eval/runs/`), and the numbers come from the eval metrics and the data layer.

Rebuild it:

```bash
GEMINI_API_KEY=... uv run python docs/video/build.py
```

- `scenes.py`: the 14 scenes, each a slide (HTML) and its narration text
- `build.py`: renders slides with headless Chromium, narrates with Gemini text-to-speech
  (voice "Charon", cached in `build/`), and assembles the MP4 with ffmpeg

The narration uses `gemini-3.8-flash-tts`. Its free tier allows 10 requests per day, so the
last three scenes were narrated with `gemini-3.1-flash-tts-preview` (same voice). Pace and
loudness match across both models.
