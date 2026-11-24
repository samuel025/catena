"""Builds the demo video (plain-language story cards over a real captured run) from a real captured run (video/capture.sh) and the narration timings (video/audio.py).
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

# ---------------------------------------------------------------- plain-language story helpers
def panel(d, box, fill=PAPER, r=16): d.rounded_rectangle(box, r, fill=fill)
def icon(d, cx, cy, ok, rad=22):
    d.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=INK if ok else EMBER)
    if ok: d.line((cx - 10, cy + 1, cx - 3, cy + 9, cx + 11, cy - 8), fill=PAPER, width=5, joint="curve")
    else: d.line((cx - 9, cy - 9, cx + 9, cy + 9), fill=PAPER, width=5); d.line((cx - 9, cy + 9, cx + 9, cy - 9), fill=PAPER, width=5)
def wrap(d, text, x, y, font, fill, width, lh):
    words, line = text.split(), ""
    for w in words:
        t = (line + " " + w).strip()
        if d.textlength(t, font=font) > width: d.text((x, y), line, font=font, fill=fill); y += lh; line = w
        else: line = t
    if line: d.text((x, y), line, font=font, fill=fill); y += lh
    return y
def proof(d, lines, y0=470, y1=626, title="From the real run"):
    d.rounded_rectangle((48, y0, W - 48, y1), 14, fill=CARBON)
    d.text((72, y0 + 12), title, font=f(SANS, 15), fill=STEEL)
    fm = f(MONO, 18); y = y0 + 40
    for ln in lines[:4]:
        ln = re.sub(r"(?<=\S) {3,}", "  ", ln)
        if len(ln) > 100: ln = ln[:99] + "…"
        d.text((72, y), ln, font=fm, fill="#c7cad6"); y += 27

def verdict(label, cards, shown, proof_lines):
    im, d = base(label)
    cw = (W - 96 - 28) // 2
    for i, (title, ok, word, detail) in enumerate(cards[:shown]):
        x = 48 + i * (cw + 28)
        panel(d, (x, 84, x + cw, 440))
        d.text((x + 32, 112), title, font=f(SANSB, 26), fill=INK)
        icon(d, x + 62, 220, ok, 32)
        d.text((x + 112, 196), word, font=f(SANSB, 54), fill=INK)
        wrap(d, detail, x + 32, 300, f(SANS, 24), PEWTER, cw - 64, 32)
    if proof_lines: proof(d, proof_lines)
    return im

def bars(d, x, y, w, val, mx, color=INK, h=26):
    d.rounded_rectangle((x, y, x + w, y + h), h // 2, fill=FOG)
    if val > 0: d.rounded_rectangle((x, y, x + max(h, int(w * val / mx)), y + h), h // 2, fill=color)

def limits(label, stage, proof_lines):
    im, d = base(label)
    panel(d, (48, 84, W - 48, 440))
    names = ["New user", "After 1st on-time repayment", "After 2nd on-time repayment"]; vals = [2, 10, 25]
    d.text((84, 108), "How much they can borrow", font=f(SANSB, 26), fill=INK)
    d.text((W - 84, 112), names[stage], font=f(SANS, 24), fill=PEWTER, anchor="ra")
    for i, net in enumerate(("Base network", "Unichain network")):
        y = 176 + i * 110
        d.text((84, y), net, font=f(SANSB, 24), fill=INK)
        bars(d, 84, y + 44, 820, vals[stage], 25, INK, 30)
        d.text((930, y + 34), str(vals[stage]), font=f(SANSB, 56), fill=INK)
    d.text((84, 400), "The repayment happens on Base. Unichain has never seen this user, and still updates within seconds." if stage else "No history yet, so only a small starter amount.", font=f(SANS, 21), fill=PEWTER)
    proof(d, proof_lines)
    return im

def story_problem(step):
    im, d = base("1 · The problem", "A credit history that follows you")
    for i, (net, line, sub) in enumerate((("Network A", "Knows you repaid 10 loans on time", "Good history"), ("Network B", "Never heard of you", "Treats you as a stranger"))):
        x = 48 + i * 606
        panel(d, (x, 120, x + 578, 360)); d.text((x + 32, 146), net, font=f(SANSB, 30), fill=INK)
        wrap(d, line, x + 32, 214, f(SANSB, 34), INK, 510, 44); d.text((x + 32, 310), sub, font=f(SANS, 22), fill=PEWTER)
    if step:
        d.rounded_rectangle((W // 2 - 150, 410, W // 2 + 150, 560), 20, fill=INK)
        d.text((W // 2, 450), "Catena", font=f(SANSB, 40), fill=PAPER, anchor="ma")
        d.text((W // 2, 506), "one history, trusted on both", font=f(SANS, 20), fill=MIST, anchor="ma")
        d.line((300, 360, W // 2 - 60, 410), fill=EMBER, width=4); d.line((W - 300, 360, W // 2 + 60, 410), fill=EMBER, width=4)
    return im

def compare(label, proof_lines):
    im, d = base(label)
    panel(d, (48, 84, W - 48, 440))
    d.text((84, 108), "Same collateral posted in both pools", font=f(SANSB, 26), fill=INK)
    rows = (("Collateral-only pool", "can borrow half of the collateral", 0.00005, MIST), ("Catena pool", "history limit + half of the collateral", 25.00005, INK))
    for i, (t, sub, v, c) in enumerate(rows):
        y = 176 + i * 120
        d.text((84, y), t, font=f(SANSB, 26), fill=INK); d.text((84, y + 36), sub, font=f(SANS, 21), fill=PEWTER)
        bars(d, 520, y + 6, 470, 0.0001 if i == 0 else v, 25.00005, c, 34)
        d.text((1015, y + 2), "0.00005" if i == 0 else "25.00005", font=f(SANSB, 34), fill=INK)
    d.text((84, 400), "Good history lets the same collateral support far more borrowing. (Collateral is demo money.)", font=f(SANS, 21), fill=PEWTER)
    proof(d, proof_lines)
    return im

def default_story(stage, proof_lines):
    im, d = base("7 · If someone doesn't repay")
    panel(d, (48, 84, W - 48, 440))
    d.text((84, 108), "How much they can borrow", font=f(SANSB, 26), fill=INK)
    d.text((W - 84, 112), ("Good standing", "Loan not repaid", "After the default")[stage], font=f(SANS, 24), fill=PEWTER, anchor="ra")
    for i, net in enumerate(("Base network", "Unichain network")):
        y = 176 + i * 110; v = 10 if stage < 2 else 0
        d.text((84, y), net, font=f(SANSB, 24), fill=INK); bars(d, 84, y + 44, 820, v, 25, INK if v else EMBER, 30)
        d.text((930, y + 34), str(v), font=f(SANSB, 56), fill=INK if v else EMBER)
    d.text((84, 400), ("A fixed rule applies the moment a default is recorded. No model can override it." if stage == 2 else "They borrowed and did not pay it back in time."), font=f(SANS, 21), fill=PEWTER)
    proof(d, proof_lines)
    return im

def safety(stage, proof_lines):
    im, d = base("8 · Safety check")
    panel(d, (48, 84, W - 48, 440))
    d.text((84, 108), "Borrow the maximum on both networks at once", font=f(SANSB, 26), fill=INK)
    for i, net in enumerate(("Base network", "Unichain network")):
        y = 170 + i * 80; d.text((84, y), net, font=f(SANSB, 22), fill=INK); bars(d, 330, y + 4, 520, 25, 25, INK, 26); d.text((880, y - 4), "25 of 25", font=f(SANSB, 34), fill=INK)
    d.text((84, 340), "Total borrowed: 50. Their limit: 50.", font=f(SANSB, 28), fill=INK)
    if stage:
        for i in range(2):
            icon(d, 112 + i * 360, 410, False, 18); d.text((144 + i * 360, 394), "Extra attempt refused", font=f(SANS, 22), fill=PEWTER)
    proof(d, proof_lines)
    return im

def honest():
    im, d = base("9 · Honest notes", "What we claim, and what we don't")
    items = (("Test networks, fake money", "Nothing here is real credit."), ("Learned from made-up data", "Real borrower data would be needed for real use."),
             ("About as accurate as a simple formula", "66.7% against 65.9%. We don't claim it's smarter."), ("Transparent and fully on-chain", "Every score is reproducible, and the code is open source."))
    for i, (t, sub) in enumerate(items):
        x = 48 + (i % 2) * 606; y = 96 + (i // 2) * 270
        panel(d, (x, y, x + 578, y + 250)); icon(d, x + 52, y + 62, i == 3, 22)
        wrap(d, t, x + 96, y + 36, f(SANSB, 30), INK, 450, 38); wrap(d, sub, x + 32, y + 150, f(SANS, 23), PEWTER, 514, 31)
    return im

def hl(im, box, text):
    d = ImageDraw.Draw(im); d.rounded_rectangle(box, 14, outline=EMBER, width=4)
    tw = d.textlength(text, font=f(SANSB, 19)) + 24
    d.rounded_rectangle((box[0], box[1] - 34, box[0] + tw, box[1] - 4), 8, fill=EMBER); d.text((box[0] + 12, box[1] - 31), text, font=f(SANSB, 19), fill=PAPER)
    return im

def dash(label, png, crop, marks):
    im = shot(label, png, crop); sc = (W - 96) / 1280
    for (sx0, sy0, sx1, sy1, text) in marks:
        box = tuple(int(v) for v in (48 + sx0 * sc, 78 + 34 + (sy0 - crop) * sc, 48 + sx1 * sc, 78 + 34 + (sy1 - crop) * sc))
        if box[1] > 120 and box[3] < 622: hl(im, box, text)
    return im

# ---------------------------------------------------------------- scenes
t1 = read("t1_before.txt"); t2 = read("t2_demo.txt"); t3 = read("t3_capital.txt"); t4 = read("t4_security.txt"); t5 = read("t5_wallets.txt")
need = lambda lines, frag: any(frag in l for l in lines) or sys.exit(f"capture does not show: {frag}")
need(t2, "quota=10000000000000000000 version=1"); need(t2, "quota=25000000000000000000 version=2"); need(t3, "collateral-only pool limit: 50000000000000")
need(t3, "25000050000000000000"); need(t4, "PASS"); need(t5, "quota=0.0  unichain quota=0.0")
short_err = lambda l: re.sub(r"Error: .*data: \"(0x[0-9a-f]{8}).*", r'Error: execution reverted (data: "\1…")', l)
hashes = [re.search(r"0x[0-9a-f]{64}", l).group(0) for l in t2 if "transactionHash" in l]
hs = lambda h: h[:10] + "…" + h[-6:]
p_before = ["$ cast send COLLATERAL_ONLY_POOL borrow(20)", short_err(t1[1]), "$ cast send CATENA_POOL borrow(20)", short_err(t1[3])]
p_s3 = [["$ script/demo.sh", "start    base: limit=2   unichain: limit=2"],
        ["$ script/demo.sh", f"repay on Base: tx {hs(hashes[1])}", "base: limit=10   unichain: limit=10   (score 557)"],
        ["$ script/demo.sh", f"repay on Base: tx {hs(hashes[3])}", "base: limit=25   unichain: limit=25   (score 600)"]]
ap = [l for l in t3 if l.startswith("transactionHash")]; txa = re.search(r"0x[0-9a-f]{64}", ap[0]).group(0) if ap else ""
p_s5 = ["$ script/demo_capital.sh", short_err(t3[2]) + "   <- collateral-only pool", f"status 1 (success), tx {hs(txa)}   <- Catena pool"]
p_s6 = [l for l in t3 if "collateral posted" in l or "pool limit" in l]
p_s7 = [["$ script/demo_wallets.sh", next(l for l in t5 if l.startswith("good standing"))[:96]], ["$ script/demo_wallets.sh", "...loan unpaid; waiting for due + grace"],
        ["$ script/demo_wallets.sh", next(l for l in t5 if l.startswith("after default"))[:96]]]
p_s8 = ["$ script/security_test.sh"] + [l for l in t4 if "reverted" in l or l.startswith(("owed", "PASS"))]
S = {  # name -> [(weight, builder)]
 "S1": [(1, lambda: story_problem(0)), (1.2, lambda: story_problem(1))],
 "S2": [(1, lambda: verdict("2 · A brand new user", [("Normal pool (needs collateral)", False, "Rejected", "No collateral posted, so the borrow of 20 is refused."), ("Catena pool", False, "Rejected", "A new user only gets a small starter amount (2).")], 1, p_before)),
        (1.2, lambda: verdict("2 · A brand new user", [("Normal pool (needs collateral)", False, "Rejected", "No collateral posted, so the borrow of 20 is refused."), ("Catena pool", False, "Rejected", "A new user only gets a small starter amount (2).")], 2, p_before))],
 "S3": [(1, lambda k=k: limits("3 · They repay on time", k, p_s3[k])) for k in range(3)],
 "S4": [(1.3, lambda: dash("4 · The dashboard", "s2_after.png", 870, [(64, 900, 535, 1385, "Trust level 2 of 3"), (551, 900, 1216, 1385, "Same limit on both networks")])),
        (1.2, lambda: dash("4 · The dashboard", "s2_after.png", 1870, [(64, 1887, 740, 2300, "What the score is based on")]))],
 "S5": [(1, lambda: verdict("5 · The loan that was refused", [("Normal pool (needs collateral)", False, "Rejected", "Same borrow of 20, still no collateral."), ("Catena pool", True, "Approved", "Their track record on the other network earned the limit.")], 2, p_s5))],
 "S6": [(1.3, lambda: compare("6 · Collateral still helps", p_s6)), (1.1, lambda: dash("6 · Collateral still helps", "s3_capital.png", 1395, [(64, 1402, 1216, 1866, "Borrowing limit = history + half the collateral")]))],
 "S7": [(1, lambda k=k: default_story(k, p_s7[k])) for k in range(3)] + [(1.1, lambda: dash("7 · If someone doesn't repay", "s4_defaulter.png", 870, [(64, 900, 535, 1385, "Suspended")]))],
 "S8": [(1, lambda: safety(0, p_s8[:1])), (1.4, lambda: safety(1, p_s8))],
 "S9": [(1, honest)],
 "S10": [(1, closing)],
}
scenes = S
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
