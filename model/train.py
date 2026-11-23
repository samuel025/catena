"""Catena credit model: synthetic data -> monotone MLP -> integer export.

Run:  .venv/bin/python model/train.py
Writes: model/weights.json, model/vectors.json, model/model_card.md, src/Mlp.sol

Everything here is deterministic (fixed seeds). The integer forward pass in `int_forward`
is the specification the Solidity library must match bit for bit.
"""
import json
import pathlib
import numpy as np

S = 1024            # fixed-point scale for features, weights, activations
SHIFT = 10          # log2(S)
H = 8               # hidden units
NF = 6
FEATURES = ["on_time", "late_ratio", "consistency", "debt_ratio", "history", "recency"]
# +1: higher feature value must never lower the score. -1: must never raise it.
SIGN = np.array([+1, -1, +1, -1, +1, +1])
# "Typical borrower" used for explanations: swap one input for these values and see how the score moves.
BASELINE = [512, 205, 614, 307, 512, 512]
TIER_T = np.array([307, 563, 819])   # score thresholds for tiers 1..3 (0.30, 0.55, 0.80 of S)
ROOT = pathlib.Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- data generation
def simulate(n, rng):
    """Generate borrower profiles. Returns integer features (n,6) and true quality y in [0,1].

    Generation rules (published in the model card):
      reliability r ~ mixture: 25% Beta(8,2) reliable, 25% Beta(2,6) unreliable, 50% Beta(3,3)
      history length k ~ U{0..20} repayments; each is late with prob (1-r)
      debt ratio d ~ Beta(2,3) (outstanding debt / approved credit)
      history age a ~ U(0,1) of the window, but a=0 if k=0
      true quality y = clip(r*(0.85+0.15*a) - 0.25*d + N(0, 0.03), 0, 1)
    A default is NOT simulated: it is a hard rule outside the model.
    """
    comp = rng.choice(3, size=n, p=[0.25, 0.25, 0.5])
    r = np.where(comp == 0, rng.beta(8, 2, n), np.where(comp == 1, rng.beta(2, 6, n), rng.beta(3, 3, n)))
    k = rng.integers(0, 21, n)
    d = rng.beta(2, 3, n)
    a = np.where(k == 0, 0.0, rng.random(n))
    X = np.zeros((n, NF), dtype=np.int64)
    for i in range(n):
        late = rng.random(k[i]) > r[i]          # True = late, in order
        c_late = int(late.sum()); c_on = int(k[i] - c_late)
        last5 = late[-5:]
        cons = int((~last5).sum())              # on-time among the last 5 (thin files score low)
        streak = 0
        for v in late[::-1]:
            if v: break
            streak += 1
        tot = c_on + c_late
        X[i] = [
            min(c_on, 10) * S // 10,
            (c_late * S // tot) if tot else 0,
            cons * S // 5,
            int(d[i] * S),
            int(a[i] * S),
            min(streak, 10) * S // 10,
        ]
    y = np.clip(r * (0.85 + 0.15 * a) - 0.25 * d + rng.normal(0, 0.03, n), 0, 1)
    return X, y


def tier_of_score(sc):
    return (sc[:, None] >= TIER_T[None, :]).sum(1)


def tier_of_y(y):
    return (y[:, None] >= (TIER_T[None, :] / S)).sum(1)


# ---------------------------------------------------------------- baseline: a plain formula
def baseline(X):
    """Hand-set weights, not fitted. Output in [0, S]."""
    x = X / S
    s = (0.35 * x[:, 0] + 0.25 * (1 - x[:, 1]) + 0.20 * x[:, 2] + 0.10 * (1 - x[:, 3])
         + 0.05 * x[:, 4] + 0.05 * x[:, 5])
    return np.clip(np.round(s * S), 0, S).astype(np.int64)


def fit_linear(X, y):
    """Strongest plain-formula opponent: least-squares linear score fitted on the same training data."""
    A = np.hstack([X / S, np.ones((len(X), 1))])
    w, *_ = np.linalg.lstsq(A, y, rcond=None)
    return w


def linear_score(X, w):
    return np.clip(np.round((np.hstack([X / S, np.ones((len(X), 1))]) @ w) * S), 0, S).astype(np.int64)


# ---------------------------------------------------------------- float MLP with sign constraints
def project(W1, W2):
    for i in range(NF):
        W1[:, i] = np.maximum(W1[:, i] * SIGN[i], 0) * SIGN[i]
    np.maximum(W2, 0, out=W2)


def train(X, y, Xv, yv, seed=1, epochs=400, lr=0.01):
    rng = np.random.default_rng(seed)
    x = X / S; xv_ = Xv / S
    W1 = rng.normal(0, 0.3, (H, NF)); project(W1, np.zeros(H))
    b1 = rng.normal(0.1, 0.1, H)
    W2 = np.abs(rng.normal(0.3, 0.1, H)); b2 = np.array([0.0])
    params = [W1, b1, W2, b2]
    m = [np.zeros_like(p) for p in params]; v = [np.zeros_like(p) for p in params]
    best, best_p = 1e9, None
    n = len(x); bs = 512
    for ep in range(epochs):
        perm = rng.permutation(n)
        for s0 in range(0, n, bs):
            idx = perm[s0:s0 + bs]; xb = x[idx]; yb = y[idx]
            z = xb @ W1.T + b1; h = np.maximum(z, 0); out = h @ W2 + b2[0]
            g = 2 * (out - yb) / len(idx)
            gW2 = h.T @ g; gb2 = np.array([g.sum()])
            gh = np.outer(g, W2) * (z > 0)
            gW1 = gh.T @ xb; gb1 = gh.sum(0)
            for j, (p, gr) in enumerate(zip(params, [gW1, gb1, gW2, gb2])):
                m[j] = 0.9 * m[j] + 0.1 * gr; v[j] = 0.999 * v[j] + 0.001 * gr * gr
                t = ep * (n // bs + 1) + s0 // bs + 1
                p -= lr * (m[j] / (1 - 0.9 ** t)) / (np.sqrt(v[j] / (1 - 0.999 ** t)) + 1e-8)
            project(W1, W2)
        if ep % 10 == 0 or ep == epochs - 1:
            ov = np.maximum(xv_ @ W1.T + b1, 0) @ W2 + b2[0]
            mse = float(np.mean((np.clip(ov, 0, 1) - yv) ** 2))
            if mse < best:
                best = mse; best_p = [p.copy() for p in params]
    return best_p, best


# ---------------------------------------------------------------- integer model (the on-chain spec)
def quantize(p):
    W1, b1, W2, b2 = p
    return (np.round(W1 * S).astype(np.int64), np.round(b1 * S).astype(np.int64),
            np.round(W2 * S).astype(np.int64), int(round(float(b2[0]) * S)))


def int_forward(X, q):
    """Bit-exact spec of Mlp.sol. Arithmetic right shift = floor division (monotone)."""
    W1, b1, W2, b2 = q
    X = np.asarray(X, dtype=np.int64)
    z = ((X @ W1.T) >> SHIFT) + b1[None, :]
    h = np.maximum(z, 0)
    out = ((h @ W2) >> SHIFT) + b2
    return np.clip(out, 0, S)


def metrics(score, y):
    tt, tp = tier_of_y(y), tier_of_score(score)
    return {
        "mse": float(np.mean((score / S - y) ** 2)),
        "tier_accuracy": float(np.mean(tt == tp)),
        "over_lending_rate": float(np.mean(tp > tt)),      # predicted tier above true tier
        "severe_over_lending_rate": float(np.mean(tp >= tt + 2)),
    }


# ---------------------------------------------------------------- properties
def monotone_check(q, rng, trials=20000):
    bad = 0
    for _ in range(trials):
        x = rng.integers(0, S + 1, NF)
        i = int(rng.integers(0, NF))
        x2 = x.copy(); x2[i] = rng.integers(x[i], S + 1)        # raise one feature
        a = int(int_forward(x[None], q)[0]); b = int(int_forward(x2[None], q)[0])
        if SIGN[i] > 0 and b < a: bad += 1
        if SIGN[i] < 0 and b > a: bad += 1
    return bad


def main():
    rng = np.random.default_rng(7)
    Xtr, ytr = simulate(30000, rng)
    Xva, yva = simulate(4000, rng)
    Xte, yte = simulate(6000, rng)

    p, vmse = train(Xtr, ytr, Xva, yva)
    q = quantize(p)
    sc_int = int_forward(Xte, q)
    W1, b1, W2, b2 = p
    sc_float = np.clip((np.maximum((Xte / S) @ W1.T + b1, 0) @ W2 + b2[0]) * S, 0, S)
    res = {
        "mlp_int": metrics(sc_int, yte),
        "mlp_float": metrics(np.round(sc_float).astype(np.int64), yte),
        "baseline_formula": metrics(baseline(Xte), yte),
        "fitted_linear": metrics(linear_score(Xte, fit_linear(Xtr, ytr)), yte),
    }
    bad = monotone_check(q, np.random.default_rng(3))
    res["monotone_violations_in_20000_random_trials"] = bad
    res["max_abs_int_vs_float_score_gap"] = float(np.max(np.abs(sc_int - sc_float)))

    # ---- exports
    W1q, b1q, W2q, b2q = q
    (ROOT / "model").mkdir(exist_ok=True)
    json.dump({"scale": S, "hidden": H, "features": FEATURES, "sign": SIGN.tolist(),
               "W1": W1q.tolist(), "b1": b1q.tolist(), "W2": W2q.tolist(), "b2": b2q,
               "tier_thresholds": TIER_T.tolist(), "baseline": BASELINE}, open(ROOT / "model/weights.json", "w"), indent=1)

    vr = np.random.default_rng(11)
    corners = [np.zeros(NF, dtype=np.int64), np.full(NF, S, dtype=np.int64)]
    for i in range(NF):
        e = np.zeros(NF, dtype=np.int64); e[i] = S; corners.append(e)
        f = np.full(NF, S, dtype=np.int64); f[i] = 0; corners.append(f)
    V = np.vstack([np.array(corners), vr.integers(0, S + 1, (300, NF))])
    json.dump({"x": V.flatten().tolist(), "y": int_forward(V, q).tolist(), "n": len(V)},
              open(ROOT / "model/vectors.json", "w"))

    write_solidity(q)
    write_card(res, vmse)
    print(json.dumps(res, indent=1))


def write_solidity(q):
    W1, b1, W2, b2 = q
    rows = ",\n".join("            [" + ", ".join(f"int256({v})" if v >= 0 else f"-int256({-v})" for v in r) + "]"
                      for r in W1)
    fmt = lambda arr: ", ".join(f"int256({v})" if v >= 0 else f"-int256({-v})" for v in arr)
    src = f"""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.29;

/// @title Mlp
/// @notice GENERATED by model/train.py. Do not edit by hand.
///         6 inputs -> {H} ReLU hidden units -> 1 output, all fixed-point with scale {S}.
///         Weights on positive features are >= 0, on negative features <= 0, hidden-to-output >= 0,
///         so the score is monotone in each input. Arithmetic right shift (floor) is monotone, and the
///         output saturates instead of wrapping.
library Mlp {{
    int256 internal constant SCALE = {S};
    uint256 internal constant SHIFT = {SHIFT};

    /// @param x six features, each in [0, SCALE]: on_time, late_ratio, consistency, debt_ratio, history, recency
    /// @return score in [0, SCALE]
    function score(int256[6] memory x) internal pure returns (uint256) {{
        int256[6][{H}] memory w1 = [
{rows}
        ];
        int256[{H}] memory b1 = [{fmt(b1)}];
        int256[{H}] memory w2 = [{fmt(W2)}];
        int256 acc;
        for (uint256 j; j < {H}; ++j) {{
            int256 z;
            for (uint256 i; i < 6; ++i) {{
                int256 xi = x[i];
                if (xi < 0) xi = 0; // inputs are clamped, so extreme values cannot overflow
                if (xi > SCALE) xi = SCALE;
                z += w1[j][i] * xi;
            }}
            z = (z >> SHIFT) + b1[j];
            if (z > 0) acc += w2[j] * z;
        }}
        int256 out = (acc >> SHIFT) + {b2};
        if (out < 0) return 0;
        if (out > SCALE) return uint256(SCALE);
        return uint256(out);
    }}

    /// @notice Typical-borrower inputs for explanations (one input is swapped for its baseline value).
    function baseline() internal pure returns (int256[6] memory b) {{
        b = [{", ".join(f"int256({v})" for v in BASELINE)}];
    }}

    /// @return tier 0..3 from the score
    function tier(uint256 s) internal pure returns (uint8) {{
        if (s >= {int(TIER_T[2])}) return 3;
        if (s >= {int(TIER_T[1])}) return 2;
        if (s >= {int(TIER_T[0])}) return 1;
        return 0;
    }}
}}
"""
    (ROOT / "src/Mlp.sol").write_text(src)


def write_card(res, vmse):
    f = lambda d: " | ".join(f"{d[k]:.4f}" for k in ["mse", "tier_accuracy", "over_lending_rate", "severe_over_lending_rate"])
    card = f"""# Catena model card

Synthetic data only. No real borrower data was used. Results below are on a held-out test set (6,000
borrowers) never used for training or model selection. Regenerate with `.venv/bin/python model/train.py`.

## Model
6 inputs -> 8 ReLU hidden units -> 1 output. Trained in float with sign-constrained weights (projected Adam),
then quantized to fixed-point integers (scale 1024) and run on-chain with integer math in `src/Mlp.sol`.

| # | Input | Direction | Definition (all integers in [0,1024]) |
|---|-------|-----------|----------------------------------------|
| 1 | on_time | higher is better | min(on-time repayments, 10) / 10 |
| 2 | late_ratio | higher is worse | late repayments / all repayments |
| 3 | consistency | higher is better | on-time repayments among the last 5 / 5 |
| 4 | debt_ratio | higher is worse | outstanding debt / approved credit |
| 5 | history | higher is better | account age / window, capped at 1 |
| 6 | recency | higher is better | on-time repayments since the last late one, capped at 10, / 10 |

Left out on purpose: raw loan volume, number of chains used. Default is a hard rule outside the model.
Tiers: score >= 307 -> 1, >= 563 -> 2, >= 819 -> 3, else 0.

## Synthetic data rules
reliability r from a mixture (25% Beta(8,2), 25% Beta(2,6), 50% Beta(3,3)); 0-20 past repayments, each late with
probability 1-r; debt ratio ~ Beta(2,3); history age uniform; true quality
y = clip(r*(0.85+0.15*age) - 0.25*debt + N(0,0.03), 0, 1). Tier targets are y thresholds 0.30 / 0.55 / 0.80.
The data encodes our own assumptions, so these numbers show the model learns the rule, not that it predicts real default.

## Results (test set)
| Model | MSE | Tier accuracy | Over-lending rate | Severe over-lending rate |
|-------|-----|---------------|-------------------|--------------------------|
| MLP (integer, on-chain) | {f(res['mlp_int'])} |
| MLP (float, reference) | {f(res['mlp_float'])} |
| Plain formula (hand-set weights) | {f(res['baseline_formula'])} |
| Linear formula fitted on the training data | {f(res['fitted_linear'])} |

Over-lending = predicted tier above the true tier. Severe = two or more tiers above.

## Properties
- Monotone violations in 20,000 random trials (raise one feature, check score): **{res['monotone_violations_in_20000_random_trials']}**.
- Max |integer score - float score| on test: {res['max_abs_int_vs_float_score_gap']:.1f} (of 1024).
- Monotonicity is per feature at the input level. It is guaranteed by sign-constrained weights, ReLU, floor rounding
  and saturation; fuzz tests are a backstop.
- Solidity parity: `test/Mlp.t.sol` checks `Mlp.score` against {'`model/vectors.json`'} (corners and random inputs).

## Limits
Synthetic data; thresholds are illustrative; address-based identity means a defaulter can start a new wallet at tier 0.
If the plain formula matches or beats the MLP in the table above, that is a real finding: the network is here because
the track asks for an on-chain model, and the formula is the honest comparison.
"""
    (ROOT / "model/model_card.md").write_text(card)


if __name__ == "__main__":
    main()
