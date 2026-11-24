"""Builds the demo video from a real captured run (video/capture.sh) and the narration timings (video/audio.py).
Stills are rendered with Pillow and joined by one ffmpeg call (2 threads, low priority). No screen recording, so it
is light on CPU and RAM. Usage: build.py work_dir audio_dir out.mp4"""
import json, pathlib, re, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
FOG, CARBON, INK, EMBER, MIST, STEEL, PEWTER, PAPER = "#f3f3f7", "#15191e", "#000000", "#ff5900", "#b9bbc6", "#8b8d98", "#6f737b", "#ffffff"
SANS = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
SANSB = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
MONO = "/home/samuel/.fonts/JetBrainsMono-Regular.ttf"
f = lambda p, s: ImageFont.truetype(p, s)

work, audio, out = map(pathlib.Path, sys.argv[1:4])
frames = work / "frames"; frames.mkdir(exist_ok=True)
T = json.load(open(audio / "timings.json")); starts, END = T["starts"], T["end"]
read = lambda n: (work / n).read_text().splitlines()

def base(label, note="Real transactions on Lasna, Base Sepolia and Unichain Sepolia. Waits trimmed."):
    im = Image.new("RGB", (W, H), FOG); d = ImageDraw.Draw(im)
    d.rounded_rectangle((32, 24, 62, 54), 9, fill=INK); d.arc((40, 31, 53, 47), 90, 270, fill=EMBER, width=3)
    d.text((72, 26), "Catena", font=f(SANSB, 24), fill=INK)
    d.text((W - 32, 30), "Reactive Meets AI", font=f(SANS, 16), fill=PEWTER, anchor="ra")
    d.rounded_rectangle((32, 646, W - 32, 698), 12, fill=PAPER)
    d.ellipse((52, 666, 62, 676), fill=EMBER)
    d.text((76, 660), label, font=f(SANSB, 22), fill=INK)
    d.text((W - 52, 664), note, font=f(SANS, 15), fill=PEWTER, anchor="ra")
    return im, d

def terminal(label, lines, shown, title):
    im, d = base(label)
    x0, y0, x1, y1 = 48, 78, W - 48, 626
    d.rounded_rectangle((x0, y0, x1, y1), 14, fill=CARBON)
    for i, c in enumerate(("#3a3f47", "#3a3f47", "#3a3f47")): d.ellipse((x0 + 20 + i * 22, y0 + 17, x0 + 32 + i * 22, y0 + 29), fill=c)
    d.text((W // 2, y0 + 14), title, font=f(SANS, 15), fill=STEEL, anchor="ma")
    fm = f(MONO, 20); lh = 30; top = y0 + 52; maxl = (y1 - top - 14) // lh
    vis = lines[:shown][-maxl:]
    for i, ln in enumerate(vis):
        y = top + i * lh
        ln = re.sub(r"(?<=\S) {3,}", "  ", ln)
        if ln.startswith("Error:") and "execution reverted" in ln:
            sel = ln.split('data: "')[1][:10] if 'data: "' in ln else ""
            ln = f'Error: Failed to estimate gas: … execution reverted, data: "{sel}…"'
        if len(ln) > 93: ln = ln[:92] + "…"
        if ln.startswith("$"): d.text((x0 + 26, y), "$", font=fm, fill=EMBER); d.text((x0 + 26 + 22, y), ln[1:].strip(), font=fm, fill=PAPER)
        else:
            col = EMBER if ln.startswith(("Error", "PASS", "  reverted (1 = yes): 1")) or "default" in ln.lower() and "reason" in ln.lower() else "#c7cad6"
            d.text((x0 + 26, y), ln, font=fm, fill=col)
    return im

def shot(label, png, crop, title="Catena dashboard · reading live from the chains"):
    im, d = base(label)
    x0, y0, x1, y1 = 48, 78, W - 48, 626
    src = Image.open(work / png).convert("RGB")
    cw = x1 - x0; sc = cw / 1280; ch = int((y1 - y0 - 34) / sc)
    c = src.crop((0, crop, 1280, min(src.height, crop + ch))).resize((cw, int(min(src.height - crop, ch) * sc)), Image.LANCZOS)
    d.rounded_rectangle((x0, y0, x1, y1), 14, fill=PAPER, outline=MIST)
    d.rounded_rectangle((x0, y0, x1, y0 + 34), 14, fill=FOG); d.rectangle((x0, y0 + 20, x1, y0 + 34), fill=FOG)
    d.text((W // 2, y0 + 8), title, font=f(SANS, 15), fill=PEWTER, anchor="ma")
    m = Image.new("L", (cw, y1 - y0 - 34), 0); ImageDraw.Draw(m).rounded_rectangle((0, -20, cw, y1 - y0 - 34), 14, fill=255)
    im.paste(c, (x0, y0 + 34), m.crop((0, 0, c.width, min(c.height, m.height))))
    return im

def cards(label, items, title=None):
    im, d = base(label, "Measured on the live deployment and in the repo")
    n = len(items); gap = 22; cw = (W - 96 - gap * (n - 1)) // n
    for i, (big, small, sub) in enumerate(items):
        x = 48 + i * (cw + gap)
        d.rounded_rectangle((x, 170, x + cw, 540), 16, fill=PAPER)
        d.text((x + 26, 205), big, font=f(SANSB, 58 if len(big) < 8 else 44), fill=INK)
        d.rectangle((x + 26, 285, x + 26 + 44, 289), fill=EMBER)
        d.text((x + 26, 312), small, font=f(SANSB, 22), fill=INK)
        yy = 356
        for ln in sub:
            d.text((x + 26, yy), ln, font=f(SANS, 18), fill=PEWTER); yy += 26
    if title: d.text((48, 96), title, font=f(SANSB, 30), fill=INK)
    return im

def closing():
    im, d = base("Catena", "Open source · MIT licensed")
    d.text((W // 2, 190), "One repayment record.", font=f(SANSB, 60), fill=INK, anchor="ma")
    d.text((W // 2, 262), "Credit on every chain.", font=f(SANSB, 60), fill=INK, anchor="ma")
    d.rectangle((W // 2 - 190, 340, W // 2 + 190, 345), fill=EMBER)
    d.text((W // 2, 392), "github.com/samuel025/catena", font=f(SANSB, 30), fill=INK, anchor="ma")
    d.text((W // 2, 446), "Addresses and the full-loop transaction hashes: docs/SUBMISSION.md", font=f(SANS, 22), fill=PEWTER, anchor="ma")
    d.text((W // 2, 480), "Test networks, fake money, synthetic training data.", font=f(SANS, 20), fill=PEWTER, anchor="ma")
    return im

# ---------------------------------------------------------------- scenes
t1 = read("t1_before.txt"); t2 = ["$ script/demo.sh"] + read("t2_demo.txt")
t3 = read("t3_capital.txt"); cut = next(i for i, l in enumerate(t3) if l.startswith("-- same borrower"))
t3a = ["$ script/demo_capital.sh"] + t3[:cut]; t3b = ["$ script/demo_capital.sh   # continued"] + t3[cut:]
t4 = ["$ script/security_test.sh"] + read("t4_security.txt")
t5 = read("t5_wallets.txt"); di = next(i for i, l in enumerate(t5) if "Defaulter" in l)
t5d = ["$ script/demo_wallets.sh   # defaulter"] + [l.lstrip("= ").strip() if l.startswith("===") else l for l in t5[di:]]
steps_for = lambda n, k: [max(1, round(n * (i + 1) / k)) for i in range(k)]

scenes = {  # name -> list of (weight, image builder)
 "S1": [(1, lambda: shot("The idea", "s0_before.png", 0, "Catena"))],
 "S2": [(2.2, lambda k=k: terminal("1 · A wallet with no history", t1, k, "terminal · fresh wallet")) for k in steps_for(len(t1), 3)] + [(1.3, lambda: shot("1 · A wallet with no history", "s0_before.png", 790))],
 "S3": [(1, lambda k=k: terminal("2 · Repay on Base, watch Unichain", t2, k, "terminal · script/demo.sh")) for k in steps_for(len(t2), 6)],
 "S4": [(1.4, lambda: shot("3 · The passport, read from the chains", "s2_after.png", 790)), (1.2, lambda: shot("3 · The passport, read from the chains", "s2_after.png", 1395))],
 "S5": [(1, lambda k=k: terminal("4 · The borrow that was refused", t3a, k, "terminal · script/demo_capital.sh")) for k in steps_for(len(t3a), 4)],
 "S6": [(1, lambda k=k: terminal("5 · Same collateral, two pools", t3b, k, "terminal · script/demo_capital.sh")) for k in steps_for(len(t3b), 4)] + [(1.4, lambda: shot("5 · Same collateral, two pools", "s3_capital.png", 1395))],
 "S7": [(1, lambda k=k: terminal("6 · A default", t5d, k, "terminal · script/demo_wallets.sh")) for k in steps_for(len(t5d), 4)] + [(1.6, lambda: shot("6 · A default", "s4_defaulter.png", 790))],
 "S8": [(1, lambda k=k: terminal("7 · Double-draw test", t4, k, "terminal · script/security_test.sh")) for k in steps_for(len(t4), 4)],
 "S9": [(1, lambda: cards("8 · The numbers, honestly", [("~190k gas", "per repay incl. 2 callbacks", ["Cap is 900k.", "One model pass is ~37k."]), ("842 events", "Python = Solidity", ["Bit-exact score, tier", "and reasons."]), ("66.7%", "MLP tier accuracy", ["Fitted linear: 65.9%.", "Synthetic data: no big win", "claimed."])]))],
 "S10": [(1, closing)],
}
order = list(scenes)
bounds = [starts[s] for s in order] + [END + 1.2]
bounds[0] = 0.0
lst, total = [], 0.0
for i, name in enumerate(order):
    span = bounds[i + 1] - bounds[i]; ws = sum(w for w, _ in scenes[name])
    for j, (w, mk) in enumerate(scenes[name]):
        p = frames / f"{name}_{j}.png"; mk().save(p, optimize=False)
        dur = span * w / ws; lst.append((p, dur)); total += dur
with open(work / "list.txt", "w") as fh:
    for p, d in lst: fh.write(f"file '{p}'\nduration {d:.3f}\n")
    fh.write(f"file '{lst[-1][0]}'\n")
print(f"{len(lst)} stills, {total:.1f}s")
cmd = ["nice", "-n", "19", "ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(work / "list.txt"),
       "-i", str(audio / "narration.mp3"), "-vf", "fps=25,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
       "-threads", "2", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.2f}", "-movflags", "+faststart", str(out)]
subprocess.run(cmd, check=True)
print("wrote", out)
