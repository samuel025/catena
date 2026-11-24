"""Pre-deployment checks on the retrained candidate (read-only). Writes model/evaluation5.md.
1. Is the retrained output a calibrated probability?  2. Does it punish recovering borrowers after they improve?
Run: nice -n 19 .venv/bin/python model/evaluate5.py
"""
import json, pathlib
import numpy as np
import train as T
import evaluate2 as E
import evaluate4 as F

ROOT = pathlib.Path(__file__).resolve().parent.parent
S = T.S


def main(epochs=60):
    rng = np.random.default_rng(2026)
    D = E.simulate_loans(9000, rng)
    tr, va, te = D["month"] < 14, (D["month"] >= 14) & (D["month"] < 17), D["month"] >= 17
    w = json.load(open(ROOT / "model/weights.json"))
    q_ship = (np.array(w["W1"]), np.array(w["b1"]), np.array(w["W2"]), w["b2"])
    q_new = E.fit_weighted(E.sub(D, tr), E.sub(D, va), 1.0, epochs)
    s_dep = T.int_forward(D["X"], q_ship).astype(np.float64); s_new = T.int_forward(D["X"], q_new).astype(np.float64)
    vs = va & (D["j"] >= 1)
    quart = [0.25, 0.5, 0.75]
    cd = [float(np.quantile(s_dep[vs], q)) for q in quart]; cn = [float(np.quantile(s_new[vs], q)) for q in quart]
    ed = F.effective(D, F.raw_tiers(s_dep, cd), 1); en = F.effective(D, F.raw_tiers(s_new, cn), 1)
    md = ["# Evaluation 5: checks before any redeploy", "", "Read-only (`model/evaluate5.py`, seeded). Synthetic data.", "",
          "## 1. Is the retrained output a probability? Reliability on test loans (scored loans only)", "",
          "| predicted P(on time) bin | loans | mean predicted | observed on-time |", "|---|---|---|---|"]
    m = te & (D["j"] >= 1); p = s_new[m] / S; y = D["y"][m]
    edges = [0, .5, .7, .8, .85, .9, .95, 1.01]
    gaps = []
    for a, b in zip(edges[:-1], edges[1:]):
        k = (p >= a) & (p < b)
        if k.sum() >= 30:
            md.append(f"| {a:.2f}-{min(b,1):.2f} | {int(k.sum())} | {p[k].mean():.3f} | {y[k].mean():.3f} |"); gaps.append(abs(p[k].mean() - y[k].mean()) * k.sum())
    ece = sum(gaps) / len(p)
    md += ["", f"Expected calibration error {ece:.3f}. Brier score {np.mean((p - y) ** 2):.3f} (always predicting the base rate {y.mean():.3f}: {np.mean((y.mean() - y) ** 2):.3f}). "
           "The deployed model's output is a quality index tuned to thresholds, not a probability; compare it with this table only as a ranking.", ""]
    md += ["## 2. Recovering borrowers: are they punished after they improve?", "",
           "Test loans of recovering borrowers, grouped by their real risk at that loan. Share given tier 2 or above and the late rate among those approved (matched-quartile operating point, existing rules).", "",
           "| real risk now | loans | deployed: approved | late among approved | retrained: approved | late among approved |", "|---|---|---|---|---|---|"]
    r = te & (D["kind"] == 5)
    for lo, hi in [(0, .15), (.15, .30), (.30, .45), (.45, 1.0)]:
        k = r & (D["pb"] >= lo) & (D["pb"] < hi)
        if k.sum() < 30: continue
        row = [f"{lo*100:.0f}-{min(hi,1)*100:.0f}%", str(int(k.sum()))]
        for e in (ed, en):
            ap = k & (e >= 2)
            row += [f"{ap.sum()/k.sum()*100:.0f}%", f"{(1-D['y'][ap].mean())*100:.0f}%" if ap.any() else "-"]
        md.append("| " + " | ".join(row) + " |")
    md += ["", "Reading: if the retrained model punished improvement, its approved share in the low-risk rows would be clearly below the deployed model's. "
           "Compare the rows above before concluding anything.", ""]
    (ROOT / "model/evaluation5.md").write_text("\n".join(md)); print("\n".join(md))


if __name__ == "__main__":
    main()
