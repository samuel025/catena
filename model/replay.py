"""Python spec of CatenaReactive's state machine, used to cross-check the contract on whole histories.

Run:  .venv/bin/python model/replay.py     (after model/train.py)
Writes model/histories.json. test/CatenaReplay.t.sol replays every event through the real contract and
compares score and tier after each one.
"""
import json
import pathlib
import numpy as np
import train as T

ROOT = pathlib.Path(__file__).resolve().parent.parent
E17 = 10 ** 17
ETH = 10 ** 18
TIER_LIMIT = [4 * ETH, 20 * ETH, 50 * ETH, 100 * ETH]
WINDOW = 86400
RAISE_PERIOD = 60
BASE_TS = 1_700_000_000
BORROW, REPAY, DEFAULT = 0, 1, 2
NO_REASON, REASON_DEFAULT = 6, 7


def popcount(v):
    return bin(v).count("1")


class Passport:
    def __init__(self):
        self.on = self.late = self.streak = 0
        self.recent_late = 0
        self.recent_count = 0
        self.defaulted = False
        self.tier = 0
        self.score = 0
        self.first_seen = 0
        self.last_raise = 0
        self.debt = 0
        self.helped = self.hurt = NO_REASON
        self.helped_d = self.hurt_d = 0


def features(p, ts):
    tot = p.on + p.late
    limit = TIER_LIMIT[p.tier]
    on_recent = p.recent_count - popcount(p.recent_late)
    age = ts - p.first_seen
    S = T.S
    return [
        min(p.on, 10) * S // 10,
        (p.late * S // tot) if tot else 0,
        on_recent * S // 5,
        min(p.debt, limit) * S // limit,
        min(age, WINDOW) * S // WINDOW,
        min(p.streak, 10) * S // 10,
    ]


def step(p, q, kind, amount, late, ts):
    """Mirror of CatenaReactive.react for one event. Returns nothing; mutates p."""
    if p.first_seen == 0:
        p.first_seen = ts
    if kind == BORROW:
        p.debt += amount
        return
    if kind == REPAY:
        p.debt = 0 if amount >= p.debt else p.debt - amount
        p.recent_late = ((p.recent_late << 1) | (1 if late else 0)) & 0x1F
        p.recent_count = min(p.recent_count + 1, 5)
        if late:
            p.late += 1; p.streak = 0
        else:
            p.on += 1; p.streak += 1
    else:
        p.defaulted = True
    x = features(p, ts)
    sc = int(T.int_forward(np.array([x]), q)[0])
    model_tier = int(T.tier_of_score(np.array([sc]))[0])
    if p.defaulted:
        new_tier = 0
    elif model_tier <= p.tier:
        new_tier = model_tier
    elif p.last_raise == 0 or ts >= p.last_raise + RAISE_PERIOD:
        p.last_raise = ts; new_tier = p.tier + 1
    else:
        new_tier = p.tier
    changed = new_tier != p.tier
    p.score = sc
    p.tier = new_tier
    if changed:
        p.helped = p.hurt = NO_REASON
        p.helped_d = p.hurt_d = 0
        if p.defaulted:
            p.hurt = REASON_DEFAULT          # hard rule, not a model sensitivity
        else:
            for i in range(6):
                x2 = list(x); x2[i] = T.BASELINE[i]
                d = sc - int(T.int_forward(np.array([x2]), q)[0])
                if d > p.helped_d: p.helped_d, p.helped = d, i
                if d < p.hurt_d: p.hurt_d, p.hurt = d, i


def main():
    w = json.load(open(ROOT / "model/weights.json"))
    q = (np.array(w["W1"]), np.array(w["b1"]), np.array(w["W2"]), w["b2"])
    rng = np.random.default_rng(21)
    out = {k: [] for k in ["seq", "kind", "amt", "late", "dt", "score", "tier", "helped", "hurt", "helped_d", "hurt_d"]}
    for seq in range(60):
        p = Passport()
        ts = BASE_TS
        reliab = rng.choice([0.95, 0.7, 0.4])
        for i in range(int(rng.integers(3, 26))):
            dt = int(rng.choice([0, 1, 30, 61, 120, 3600, 20000]))
            ts += dt
            r = rng.random()
            if p.defaulted and r < 0.7:
                kind = REPAY
            elif r < 0.08 and p.debt > 0:
                kind = DEFAULT
            elif r < 0.45:
                kind = BORROW
            else:
                kind = REPAY
            amount = int(rng.integers(1, 41)) * E17
            late = bool(rng.random() > reliab)
            step(p, q, kind, amount, late, ts)
            for k, v in zip(out, [seq, kind, amount // E17, int(late), dt, p.score, p.tier,
                                  p.helped, p.hurt, p.helped_d, p.hurt_d]):
                out[k].append(v)
    out["n"] = len(out["seq"])
    json.dump(out, open(ROOT / "model/histories.json", "w"))
    tiers = np.bincount(out["tier"], minlength=4)
    print(f"{out['n']} events in 60 histories; tier counts after each event: {tiers.tolist()}")


if __name__ == "__main__":
    main()
