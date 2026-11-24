"""Extra evaluations of the shipped model. Does not change weights.

Run:  .venv/bin/python model/evaluate.py     (after model/train.py). Writes model/evaluation.md.

A. Risky borrowers: how often does each scorer approve borrowers whose true quality is below the tier-1 bar?
B. Unseen profiles: train on two of the three borrower populations, test on the third (leave one population out).
C. A transparent binned scorecard next to the MLP, the fitted linear formula and the hand-set formula.

Caveat for all of it: the data is synthetic and its true quality is a near-linear function of the features, so a
linear formula has little to lose. Nothing here shows how the model would do on real borrowers.
"""
import json
import pathlib
import numpy as np
import train as T

ROOT = pathlib.Path(__file__).resolve().parent.parent
S = T.S
NAMES = ["reliable Beta(8,2)", "unreliable Beta(2,6)", "mixed Beta(3,3)"]


def scorecard(X):
    """Hand-set points table (max 100), tier cut-offs at 30 / 55 / 80 like the model."""
    on = X[:, 0] * 10 // S            # 0..10 on-time repayments (capped)
    late = X[:, 1] / S
    cons = X[:, 2] * 5 // S           # 0..5 of the last five on time
    debt = X[:, 3] / S
    hist = X[:, 4] / S
    streak = X[:, 5] * 10 // S
    pts = (np.select([on >= 10, on >= 3], [30, 15], 0)
           + np.select([late > 0.5, late > 0.2, late > 0.05], [0, 12, 22], 30)
           + np.select([cons >= 5, cons >= 4, cons >= 3], [20, 15, 8], 0)
           + np.select([debt > 0.7, debt > 0.4], [0, 5], 10)
           + np.where(hist > 0.5, 5, 0) + np.where(streak >= 5, 5, 0))
    return (pts * S // 100).astype(np.int64)


def tiers(sc):
    return T.tier_of_score(sc)


def row(name, sc, y):
    m = T.metrics(sc, y)
    tt, tp = T.tier_of_y(y), tiers(sc)
    bad = tt == 0
    return {"name": name, "mse": m["mse"], "acc": m["tier_accuracy"], "over": m["over_lending_rate"],
            "severe": m["severe_over_lending_rate"],
            "risky_n": int(bad.sum()),
            "risky_false_approval": float(np.mean(tp[bad] > 0)) if bad.any() else float("nan"),
            "risky_recall": float(np.mean(tp[bad] == 0)) if bad.any() else float("nan")}


def table(rows):
    out = ["| scorer | MSE | tier acc | over-lend | severe over-lend | true tier 0: wrongly approved |", "|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['name']} | {r['mse']:.4f} | {r['acc']*100:.1f}% | {r['over']*100:.1f}% | {r['severe']*100:.1f}% | {r['risky_false_approval']*100:.1f}% of {r['risky_n']} |")
    return "\n".join(out)


def main():
    w = json.load(open(ROOT / "model/weights.json"))
    q = (np.array(w["W1"]), np.array(w["b1"]), np.array(w["W2"]), w["b2"])

    # same draw order as train.py, so the test set is the one in the model card
    rng = np.random.default_rng(7)
    Xtr, ytr = T.simulate(30000, rng)
    T.simulate(4000, rng)
    Xte, yte = T.simulate(6000, rng)
    lin = T.fit_linear(Xtr, ytr)

    md = ["# Extra evaluations", "", "Synthetic data only. Reproduce with `model/evaluate.py`.", ""]
    rowsA = [row("MLP (shipped, integer)", T.int_forward(Xte, q), yte),
             row("fitted linear", T.linear_score(Xte, lin), yte),
             row("transparent scorecard", scorecard(Xte), yte),
             row("hand-set formula", T.baseline(Xte), yte)]
    md += ["## A. Risky borrowers, same held-out set as the model card (6000 profiles)", "",
           "No defaults are simulated (a default is a hard rule), so 'risky' means true quality below the tier-1 bar. "
           "The last column is the share of those borrowers a scorer would approve for credit.", "", table(rowsA), ""]

    md += ["## B. Unseen borrower populations", "",
           "The generator mixes three populations of borrowers. For each row the models are trained on the other two "
           "and tested on the one left out (shipped hyper-parameters, 12000 training profiles, 200 epochs, so the "
           "numbers differ a little from section A).", ""]
    for held in range(3):
        p_tr = [0.0 if i == held else 1.0 for i in range(3)]
        p_tr = [v / sum(p_tr) for v in p_tr]
        p_te = [1.0 if i == held else 0.0 for i in range(3)]
        r = np.random.default_rng(100 + held)
        X1, y1 = T.simulate(12000, r, p_tr); Xv, yv = T.simulate(2000, r, p_tr); X2, y2 = T.simulate(4000, r, p_te)
        pp, _ = T.train(X1, y1, Xv, yv, epochs=200)
        qq = T.quantize(pp)
        l2 = T.fit_linear(X1, y1)
        rows = [row("MLP (integer)", T.int_forward(X2, qq), y2),
                row("fitted linear", T.linear_score(X2, l2), y2),
                row("transparent scorecard", scorecard(X2), y2)]
        md += [f"### Held out: {NAMES[held]}", "", table(rows), ""]
        print(NAMES[held], [(r_['name'], round(r_['mse'], 4), round(r_['acc'], 3)) for r_ in rows])

    md += ["## Reading this", "",
           "- Monotonicity (more on-time repayments never lowers a score, more late ones never raise it) is a safety "
           "property. It does not make the scores accurate.",
           "- The true quality in the generator is close to linear in the features, so a fitted linear formula is a "
           "strong opponent and the MLP's edge, if any, is small. We do not claim a large accuracy win.",
           "- 'Wrongly approved' is the number a lender should care about most. Compare it across rows before "
           "trusting any single accuracy figure.", ""]
    (ROOT / "model/evaluation.md").write_text("\n".join(md))
    print("\n".join(md[:14]))


if __name__ == "__main__":
    main()
