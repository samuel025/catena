# Demo video tooling

The video is assembled from a **real run** (command output and dashboard screenshots captured from the live deployment)
plus one continuous voice-over, so it is light on CPU and RAM: no screen recording, one process at a time, low priority.

1. `capture.sh <dir>`: runs the demo scripts on fresh wallets (about 1 lREACT), filters secrets, takes dashboard screenshots.
   Needs the page served (`cd web && python3 -m http.server 8080`) and Chrome.
2. `audio.py narration.txt <dir>`: synthesizes the whole script in **one** request with a Microsoft neural voice (edge-tts,
   the Edge read-aloud service, no API key) and records word timings so scenes start exactly with their narration.
3. `build.py <capture dir> <audio dir> out.mp4`: renders stills with Pillow and joins them with one ffmpeg call
   (2 threads, `nice 19`). Takes about 20 seconds.

Install: `python3 -m venv v && v/bin/pip install edge-tts pillow`. Waits in the demo scripts are trimmed by the stills;
the on-screen caption says so.
