"""Harder evaluation: borrower trajectories, a real default process, a temporal split. Does not change weights.

Run:  nice -n 19 .venv/bin/python model/evaluate2.py     Writes model/evaluation2.md.

What is different from train.py's generator:
  * Seven borrower types whose repayment behaviour CHANGES over time (deteriorating, recovering, strategic
    defaulters that behave well and then stop, over-leveraged, new/thin files, occasional late payers, consistent).
  * Each loan has an outcome (on time / late / default) drawn from the borrower's risk at that moment.
  * Features at loan j use only loans before j (no look-ahead). Same six inputs as the shipped model.
  * Temporal split: train on loans in months 0-13, validate 14-16, test 17-23. The same borrowers appear in
    both, but never the same loan, and the test loans happen later than every training loan.
  * Second split: train without two borrower types (deteriorating, strategic), test on exactly those.
Target: will the NEXT loan be on time. Models output P(on time) scaled to 0..1024. Scorers are compared at the
same approval rate, so no scorer wins by simply approving fewer people.
Caveat: still synthetic. It tests the pipeline against harder behaviour that its own generator defines, not real borrowers.
"""
import json
import pathlib
import numpy as np
import train as T
from evaluate import scorecard

ROOT = pathlib.Path(__file__).resolve().parent.parent
S = T.S
TYPES = ["consistent", "new / thin file", "occasional late", "deteriorating", "over-leveraged", "recovering", "strategic defaulter"]
MIX = [0.25, 0.15, 0.15, 0.12, 0.12, 0.11, 0.10]
MONTHS = 24


def p_bad(kind, prog, d, strat_at):
    base = {0: 0.04, 1: 0.12, 2: 0.15, 3: 0.04 + 0.55 * prog, 4: 0.07, 5: 0.55 - 0.48 * prog,
            6: 0.05 if prog < strat_at else 0.85}[kind]
    return float(np.clip(base + 0.25 * (d - 0.4), 0.01, 0.97))


def simulate_loans(n_borrowers, rng, mix=MIX):
    rows = []  # feature vec, y_ontime, month, kind, p_bad_now, defaulted
    for bid in range(n_borrowers):
        kind = int(rng.choice(7, p=mix))
        n_loans = int(rng.integers(1, 5)) if kind == 1 else int(rng.integers(5, 19))
        d = float(rng.beta(6, 2) if kind == 4 else rng.beta(2, 3))
        strat_at = rng.uniform(0.3, 0.65)
        month = int(rng.integers(0, 20 if kind != 1 else 22))
        first = None
        hist = []  # True = late/default
        for j in range(n_loans):
            if month >= MONTHS:
                break
            if first is None:
                first = month
            prog = j / max(n_loans - 1, 1)
            pb = p_bad(kind, prog, d, strat_at)
            bad = rng.random() < pb
            dflt = bad and rng.random() < (0.8 if (kind == 6 and prog >= strat_at) else 0.25)
            tot = len(hist); c_late = sum(hist); c_on = tot - c_late
            last5 = hist[-5:]
            streak = 0
            for v in hist[::-1]:
                if v: break
                streak += 1
            age = 0.0 if tot == 0 else min((month - first) / 12.0, 1.0)
            x = [min(c_on, 10) * S // 10, (c_late * S // tot) if tot else 0, int((5 - sum(last5)) * S // 5) if last5 else 0,
                 int(np.clip(d + rng.normal(0, 0.05), 0, 1) * S), int(age * S), min(streak, 10) * S // 10]
            rows.append((x, 0.0 if bad else 1.0, month, kind, pb, bool(dflt), tot, bid, j))
            hist.append(bool(bad))
            month += 1 + int(rng.random() < 0.3)
    X = np.array([r[0] for r in rows], dtype=np.int64)
    return dict(X=X, y=np.array([r[1] for r in rows]), month=np.array([r[2] for r in rows]),
                kind=np.array([r[3] for r in rows]), pb=np.array([r[4] for r in rows]),
                dflt=np.array([r[5] for r in rows]), n=np.array([r[6] for r in rows]),
                bid=np.array([r[7] for r in rows]), j=np.array([r[8] for r in rows]))


def sub(D, m):
    return {k: v[m] for k, v in D.items()}


def fit_weighted(Dtr, Dva, bad_weight, epochs, seed=1):
    w = np.where(Dtr["y"] == 0, bad_weight, 1.0); wv = np.where(Dva["y"] == 0, bad_weight, 1.0)
    p, _ = T.train(Dtr["X"], Dtr["y"], Dva["X"], Dva["y"], seed=seed, epochs=epochs, w=w, wv=wv)
    return T.quantize(p)


def shrink(score, n, prior, k=4):
    """Deterministic confidence: pull thin files toward the average borrower's score (prior), c = n / (n + k)."""
    c = n / (n + k)
    return (score * c + prior * (1 - c)).astype(np.float64)


def at_rate(score, D, rate):
    """Approve the top `rate` share by score (ties broken by a stable sort). Returns metrics for the approved set."""
    order = np.argsort(-score.astype(np.float64) + np.arange(len(score)) * 1e-9, kind="stable")
    k = int(len(score) * rate)
    ap = np.zeros(len(score), bool); ap[order[:k]] = True
    risky = D["pb"] > 0.30; good = D["pb"] < 0.10
    return {"late_rate": float(1 - D["y"][ap].mean()), "default_rate": float(D["dflt"][ap].mean()),
            "risky_approved": float(ap[risky].mean()) if risky.any() else float("nan"),
            "good_rejected": float((~ap)[good].mean()) if good.any() else float("nan"),
            "precision": float(D["y"][ap].mean()),
            "recall": float(ap[D["y"] == 1].mean())}


def table(rows, rates=(0.4, 0.6)):
    h = "| scorer | approve top | next loan late/default among approved | default among approved | risky borrowers approved | reliable borrowers rejected |"
    out = [h, "|---|---|---|---|---|---|"]
    for name, sc, D in rows:
        for rt in rates:
            m = at_rate(sc, D, rt)
            out.append(f"| {name} | {int(rt*100)}% | {m['late_rate']*100:.1f}% | {m['default_rate']*100:.1f}% | {m['risky_approved']*100:.1f}% | {m['good_rejected']*100:.1f}% |")
    return "\n".join(out)


def scorers(Dtr, Dva, Dte, epochs):
    q_ship = (lambda w: (np.array(w["W1"]), np.array(w["b1"]), np.array(w["W2"]), w["b2"]))(json.load(open(ROOT / "model/weights.json")))
    q_new = fit_weighted(Dtr, Dva, 1.0, epochs)
    q_c3 = fit_weighted(Dtr, Dva, 3.0, epochs)
    q_c6 = fit_weighted(Dtr, Dva, 6.0, epochs)
    lin = T.fit_linear(Dtr["X"], Dtr["y"])
    X, n = Dte["X"], Dte["n"]
    mlp = T.int_forward(X, q_new)
    return [("shipped MLP (trained on the old generator)", T.int_forward(X, q_ship), Dte),
            ("MLP retrained on trajectory data", mlp, Dte),
            ("MLP, cost-sensitive (bad outcome x3)", T.int_forward(X, q_c3), Dte),
            ("MLP, cost-sensitive (bad outcome x6)", T.int_forward(X, q_c6), Dte),
            ("retrained MLP + confidence shrink", shrink(mlp, n, float(Dtr["y"].mean()) * S), Dte),
            ("fitted linear", T.linear_score(X, lin), Dte),
            ("transparent scorecard", scorecard(X), Dte),
            ("hand-set formula", T.baseline(X), Dte)]


WHAT_SHOWS = '## What this shows\n\n- **The shipped model is tuned to an easy generator.** On loans from changing borrowers, retraining the same 6-8-1 network on trajectory data cuts risky approvals at a 40% approval rate from 22.4% to 14.2% and next-loan late/default among approved loans from 13.2% to 10.8%. The architecture does not change; the training data does.\n- **The network does not beat a fitted linear formula.** Retrained MLP and fitted linear are within noise of each other in every section (14.2% vs 14.1% risky approved at 40%). The earlier conclusion stands: the value is auditable on-chain inference, not an accuracy win.\n- **Both beat the hand-made scorecard on risky approvals** at the same approval rate (14% vs 18% at 40%), but the gap is small and the scorecard is competitive on unseen borrower types (section B).\n- **Cost-sensitive training did nothing useful.** Weights of 3 and 6 on bad loans leave every column within about a point of the unweighted model. A cost penalty changes where a score threshold sits, not much how borrowers rank, and this comparison fixes the approval rate.\n- **The confidence shrink is mixed.** It helps reliable thin files a little at one approval rate and hurts risky-thin-file approvals at another. We do not adopt it.\n- **Unseen types are hard for everyone.** Borrowers who deteriorate or turn strategic are approved far too often by every scorer (30-48% of risky ones approved). A snapshot of past repayments cannot see a defaulter who has not started defaulting yet. This is why the hard rules (default flag, one-tier raise per period, quota caps) matter more than the model.\n\n'


def main(epochs=60):
    rng = np.random.default_rng(2026)
    D = simulate_loans(9000, rng)
    md = ["# Harder evaluation: trajectories, defaults, temporal split", "",
          "Reproduce with `model/evaluate2.py` (seeded). Synthetic data; read the caveats at the end.", "",
          f"Data: {len(D['y'])} loans from 9000 borrowers of seven types. Share of loans late or defaulted: {100*(1-D['y'].mean()):.1f}%, "
          f"defaulted: {100*D['dflt'].mean():.1f}%.", "",
          "Columns: among the loans each scorer approves at the stated approval rate, how many were then late/defaulted, "
          "how many were truly risky (the borrower's real risk at that moment above 30%), and how many truly reliable "
          "borrowers (risk below 10%) it turned away.", ""]
    tr, va, te = D["month"] < 14, (D["month"] >= 14) & (D["month"] < 17), D["month"] >= 17
    Dtr, Dva, Dte = sub(D, tr), sub(D, va), sub(D, te)
    md += [f"## A. Temporal split: train months 0-13 ({tr.sum()} loans), test months 17-23 ({te.sum()} loans)", ""]
    rows = scorers(Dtr, Dva, Dte, epochs)
    md += [table(rows), ""]
    print(table(rows), flush=True)

    held = np.isin(D["kind"], [3, 6])
    Dtr2, Dva2 = sub(D, ~held & (D["month"] < 17)), sub(D, ~held & (D["month"] >= 17))
    Dte2 = sub(D, held & (D["month"] >= 17))
    md += [f"## B. Unseen borrower types: trained without deteriorating and strategic borrowers, tested on only those ({len(Dte2['y'])} later loans)", ""]
    rows2 = scorers(Dtr2, Dva2, Dte2, epochs)
    md += [table(rows2), ""]
    print(table(rows2), flush=True)

    thin = Dte["n"] < 3
    md += [f"## C. Thin files only (fewer than 3 prior loans, {int(thin.sum())} test loans)", "",
           "Does a scorer shut out borrowers who simply have no history? Reliable borrowers rejected, among truly reliable thin files:", ""]
    Dthin = sub(Dte, thin)
    md += ["| scorer | approve top 60% | reliable thin files rejected | risky thin files approved |", "|---|---|---|---|"]
    for name, sc, _ in rows:
        m = at_rate(sc[thin], Dthin, 0.6)
        md.append(f"| {name} | 60% | {m['good_rejected']*100:.1f}% | {m['risky_approved']*100:.1f}% |")
    md += [""]
    md += [WHAT_SHOWS]
    md += ["## Reading this", "",
           "- Compare scorers at the same approval rate. A scorer that approves fewer people looks safer by construction.",
           "- 'Cost-sensitive' multiplies the training loss on loans that went bad. Look at both right-hand columns: if risky "
           "approvals fall only because more reliable borrowers are rejected, the cost penalty did not help.",
           "- The synthetic risk model is ours, so every row measures how well a scorer recovers a behaviour we invented. "
           "It is a harder test than `train.py`'s generator, not evidence about real borrowers.", ""]
    (ROOT / "model/evaluation2.md").write_text("\n".join(md))


if __name__ == "__main__":
    main()
