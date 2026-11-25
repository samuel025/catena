"""Matched-approval comparison of the deployed model, the retrained six-feature model and the recent-window candidate.
Evaluation only. Run: nice -n 19 .venv/bin/python model/evaluate7.py   Writes model/evaluation7.md.
Each model's cut-offs are shifted on VALIDATION data until it approves (tier >= 2, contract rules) the target share of loans;
the test set (months 17-23) is then evaluated once, so models are compared at the same lending volume.
Candidate = evaluate6's selection (six features + recent late ratio + trend, window 5), 3 training seeds averaged.
"""
import json, pathlib
import numpy as np
import train as T
import evaluate2 as E
import evaluate4 as F
import evaluate6 as G

ROOT = pathlib.Path(__file__).resolve().parent.parent
S = T.S


def at_target(D, s, va, te, target):
    vs = va & (D["j"] >= 1)
    cuts = [float(np.quantile(s[vs], q)) for q in (0.25, 0.5, 0.75)]
    off = F.match_offset(D, s, cuts, target, va, 2)
    eff = F.effective(D, F.raw_tiers(s.astype(np.float64) + off, cuts), 1)
    def sel(mk):
        Dk = E.sub(D, mk); r = F.metrics(Dk, eff[mk], 2); ap = eff[mk] >= 2
        r["precision"] = float(Dk["y"][ap].mean()); r["recall"] = float(ap[Dk["y"] == 1].mean()); return r
    out = {"all": sel(te), "det": sel(te & (D["kind"] == 3)), "str": sel(te & (D["kind"] == 6))}
    rec = te & (D["kind"] == 5) & (D["pb"] < 0.30); out["rec"] = float((eff[rec] >= 2).mean())
    return out


def main():
    rng = np.random.default_rng(2026)
    D = E.simulate_loans(9000, rng)
    tr, va, te = D["month"] < 14, (D["month"] >= 14) & (D["month"] < 17), D["month"] >= 17
    sign6 = np.array([+1, -1, +1, -1, +1, +1])
    rec, trd = G.extra_features(D, 5); X8 = np.hstack([D["X"], rec[:, None], trd[:, None]]); sign8 = np.append(sign6, [-1, +1])
    w0 = json.load(open(ROOT / "model/weights.json"))
    s_dep = [T.int_forward(D["X"], (np.array(w0["W1"]), np.array(w0["b1"]), np.array(w0["W2"]), w0["b2"]))]
    s6 = [T.int_forward(D["X"], G.train_n(D["X"][tr], D["y"][tr], D["X"][va], D["y"][va], sign6, sd)) for sd in G.SEEDS]
    s8 = [T.int_forward(X8, G.train_n(X8[tr], D["y"][tr], X8[va], D["y"][va], sign8, sd)) for sd in G.SEEDS]
    md = ["# Evaluation 7: approval-rate targets chosen on validation, compared on test", "",
          "Evaluation only (`model/evaluate7.py`, seeded). Synthetic data. Each model is approved at the same share of loans (tier 2 or above under the contract rules); "
          "cut-offs were set on validation, test evaluated once. Mean of 3 seeds for the two retrained models.", "",
          "| target approval | model | actual test approval | overall risky approved | false rejection | precision | recall | loss per loan | recovering low-risk approved | deteriorating risky approved | strategic risky approved |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for tgt in (0.30, 0.40, 0.50):
        for name, ss in (("deployed", s_dep), ("retrained six features", s6), ("candidate: + recent ratio + trend", s8)):
            rs = [at_target(D, s, va, te, tgt) for s in ss]
            g = lambda f: float(np.mean([f(r) for r in rs]))
            md.append(f"| {int(tgt*100)}% | {name} | {g(lambda r: r['all']['approval'])*100:.1f}% | {g(lambda r: r['all']['risky_approved'])*100:.1f}% | {g(lambda r: r['all']['false_rejection'])*100:.1f}% | "
                      f"{g(lambda r: r['all']['precision'])*100:.1f}% | {g(lambda r: r['all']['recall'])*100:.1f}% | {g(lambda r: r['all']['loss_per_loan']):.2f} | {g(lambda r: r['rec'])*100:.1f}% | "
                      f"{g(lambda r: r['det']['risky_approved'])*100:.1f}% | {g(lambda r: r['str']['risky_approved'])*100:.1f}% |")
    md += ["", "## Reading this", "",
           "- Matching on validation does not transfer exactly: test approval rates still differ by up to 3 points, and the deployed model approves slightly more at every target. Read the 'actual test approval' column.",
           "- At the 40% target the candidate approves 15.1% of truly risky loans against 27.6% for the deployed model, and 18.4% against 40.5% of deteriorating borrowers, while approving about as many low-risk recovering loans (24.7% against 25.3%). The six-feature retrained model has the same risk gains but approves only 4.9% of recovering loans.",
           "- Its false rejection is 32.6% against 29.5% for the deployed model, at 3.6 points lower approval, so part of that gap is volume.",
           "- Loss per loan is noisy across targets (a few strategic-defaulter loans at a 100-unit limit dominate it); do not read small differences.",
           "- All of this is the simulator's own behaviour. It does not show how the candidate would do on real borrowers, and the deployed model remains the six-input one.", ""]
    (ROOT / "model/evaluation7.md").write_text("\n".join(md) + "\n"); print("\n".join(md))


if __name__ == "__main__":
    main()
