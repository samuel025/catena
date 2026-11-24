"""Narration with Microsoft's neural voices through edge-tts (the Edge read-aloud service; no API key).
The whole script is synthesized in ONE request so intonation carries across sentences (no sentence-by-sentence pauses),
and word boundaries tell build.py exactly when each scene starts. Usage: audio.py narration.txt out_dir [voice] [rate]"""
import asyncio, json, re, sys, pathlib
import edge_tts

src, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
voice = sys.argv[3] if len(sys.argv) > 3 else "en-US-AndrewMultilingualNeural"
rate = sys.argv[4] if len(sys.argv) > 4 else "+4%"
scenes, cur = {}, None
for line in src.read_text().splitlines():
    m = re.match(r"\[\[(S\d+)\]\]", line.strip())
    if m: cur = m.group(1); scenes[cur] = []
    elif line.strip() and cur: scenes[cur].append(line.strip())
text = " ".join(" ".join(v) for v in scenes.values())

async def main():
    comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    audio, words = bytearray(), []
    async for ch in comm.stream():
        if ch["type"] == "audio": audio += ch["data"]
        elif ch["type"] == "WordBoundary": words.append({"t": ch["text"], "start": ch["offset"] / 1e7, "dur": ch["duration"] / 1e7})
    (out / "narration.mp3").write_bytes(bytes(audio))
    # scene start = first word of the scene found in order in the boundary stream
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    toks = [norm(w["t"]) for w in words]; pos = 0; starts = {}
    for name, lines in scenes.items():
        first = [norm(x) for x in " ".join(lines).split()][:3]
        for i in range(pos, len(toks) - 2):
            if toks[i:i + 3] == first: starts[name] = words[i]["start"]; pos = i + 1; break
        else: raise SystemExit(f"could not locate {name}: {first}")
    end = words[-1]["start"] + words[-1]["dur"]
    json.dump({"starts": starts, "end": end, "words": len(words)}, open(out / "timings.json", "w"), indent=1)
    print(json.dumps({"starts": starts, "end": end, "words": len(words)}))
asyncio.run(main())
