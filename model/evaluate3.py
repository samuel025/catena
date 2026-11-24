"""Evidence-first follow-up to evaluate2.py. Does not change weights, features, training or contracts.

Run:  nice -n 19 .venv/bin/python model/evaluate3.py     Writes model/evaluation3.md.

Questions:
 1. Per borrower type, at ONE global approval rate: how do the deployed MLP, retrained MLP, fitted linear and scorecard do?
 2. Do the six existing features separate deteriorating and strategic borrowers from reliable ones, and how early?
 3. How many loans after a borrower becomes risky does each scorer take to stop approving them?
 4. Is there temporal leakage, and do the "unseen" test types really contain behaviour absent from training?
"""
import json
import pathlib
import numpy as np
import train as T
import evaluate2 as E
from evaluate import scorecard

ROOT = pathlib.Path(__file__).resolve().parent.parent
S = T.S
KT = E.TYPES
RATE = 0.5


FINDINGS = "\n## What the evidence says\n\n- **Strategic defaulters cannot be caught by any history-based scorer on their first bad loan.** Until the turn, their late ratio, streak and on-time count look exactly like a reliable borrower's (late ratio about 50-60 on a 1024 scale, flat). One loan after the turn the retrained score drops and approval falls from 76% to 13%. The exposure is one loan. That is an information limit, not a model flaw, and it is what the per-chain quota caps and the default rule are for.\n- **Deteriorating borrowers do leave a trace, and the retrained model uses it; the deployed one does not.** The late ratio climbs from about 53 to 152 before the turn. Retrained approvals fall 87% to 44% over the four loans before it (AUC 0.89 on high- versus low-risk loans). The deployed network scores them AUC 0.44, below chance: it rewards the growing on-time count and history length more than it penalises the rising late ratio, so it approves 43% of the risky ones. That is a real weakness of the deployed weights, found only on this harder data.\n- **The retrained model is not a drop-in replacement.** It gives a wallet with no history a mean score of 853 (tier 3) and approves 90% of first loans, because the typical borrower in this data is reliable. The deployed model scores them 401 and approves none. That contradicts the thin-file policy (starter quota, one tier per period). Retraining would need a policy cap on thin files first. It also explains why the retrained model does worse than the deployed one on recovering borrowers (43% late among approved versus 20%): their risky loans are early, when history is thin.\n- **No look-ahead leakage in the features** (0 mismatches). The temporal split holds. Test loans share borrowers with training loans (56%), which is realistic for a live system but is not a population holdout. Section B's held-out types really are novel: 0% of training borrowers show a risk rise of more than 30 points, against 82% of the held-out types.\n- **Decision input, not a decision.** The deployed model's blind spot to deterioration is real but bounded in practice by the hard rules: late repayments are visible on-chain and a tier cut is immediate, the quota caps exposure per chain, and one default zeroes the unsecured limit. We have not changed weights, features, training or the deployment.\n"


def auc(pos, neg):
    """P(score of a random positive > score of a random negative); ties count half."""
    x = np.concatenate([pos, neg]); r = np.empty(len(x)); order = np.argsort(x, kind="mergesort")
    xs = x[order]; ranks = np.arange(1, len(x) + 1, dtype=float)
    # average ranks for ties
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[j + 1] == xs[i]: j += 1
        ranks[i:j + 1] = (i + j) / 2 + 1; i = j + 1
    r[order] = ranks
    return (r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def thr_for_rate(score, rate):
    return np.quantile(score.astype(np.float64), 1 - rate)


def main(epochs=60):
    rng = np.random.default_rng(2026)
    D = E.simulate_loans(9000, rng)       # identical draw to evaluate2.py
    tr, va, te = D["month"] < 14, (D["month"] >= 14) & (D["month"] < 17), D["month"] >= 17
    Dtr, Dva, Dte = E.sub(D, tr), E.sub(D, va), E.sub(D, te)
    q_ship = (lambda w: (np.array(w["W1"]), np.array(w["b1"]), np.array(w["W2"]), w["b2"]))(json.load(open(ROOT / "model/weights.json")))
    q_new = E.fit_weighted(Dtr, Dva, 1.0, epochs)
    lin = T.fit_linear(Dtr["X"], Dtr["y"])
    models = {"deployed MLP": lambda X: T.int_forward(X, q_ship), "retrained MLP": lambda X: T.int_forward(X, q_new),
              "fitted linear": lambda X: T.linear_score(X, lin), "scorecard": scorecard}
    md = ["# Evaluation 3: where do the scorers fail, and why?", "",
          "Evidence only. No features, weights, training or contracts were changed. Reproduce with `model/evaluate3.py` (seeded; "
          "same simulated loans as `evaluate2.py`). Synthetic data throughout.", ""]

    # ---------------- 1. per type, one global approval rate
    sc_te = {k: f(Dte["X"]) for k, f in models.items()}
    thr = {k: thr_for_rate(v, RATE) for k, v in sc_te.items()}
    appr = {k: sc_te[k] >= thr[k] for k in models}
    md += [f"## 1. Per borrower type, test months 17-23, each scorer approves the top {int(RATE*100)}% of ALL test loans", "",
           "Per cell: share of the type's truly risky loans (real risk > 30% at that moment) that were approved / "
           "share of approved loans of that type that went late or defaulted. The approval threshold is global, so a scorer "
           "cannot look good on one type by being stricter overall.", "",
           "| type | test loans | truly risky | " + " | ".join(models) + " |", "|---|---|---|" + "---|" * len(models)]
    for k in range(7):
        m = Dte["kind"] == k
        risky = m & (Dte["pb"] > 0.30)
        cells = []
        for name in models:
            ap = appr[name] & m
            ra = float(appr[name][risky].mean()) * 100 if risky.any() else float("nan")
            la = (1 - Dte["y"][ap].mean()) * 100 if ap.any() else float("nan")
            cells.append(("no risky loans" if not risky.any() else f"{ra:.0f}%") + f" / {la:.0f}%")
        md.append(f"| {KT[k]} | {int(m.sum())} | {int(risky.sum())} | " + " | ".join(cells) + " |")
    md += [""]

    # ---------------- 2/3. event study around the turn to risky, using the temporal-split retrained model on ALL loans
    S_all = {k: f(D["X"]) for k, f in models.items()}
    thr_all = {k: thr_for_rate(S_all[k][te], RATE) for k in models}   # threshold fixed on test months, applied everywhere
    md += ["## 2. Do the six features see it coming? Event study around the first loan where real risk exceeds 30%", ""]
    for k in (3, 6, 0):
        idxs = np.where(D["kind"] == k)[0]
        by = {}
        for i in idxs: by.setdefault(int(D["bid"][i]), []).append(i)
        if k == 0:
            md += ["Reference: consistent borrowers (never risky), averaged by loan number.", "",
                   "| loan number | mean retrained score | mean on-time | mean late ratio | mean recency | approved (retrained) |", "|---|---|---|---|---|---|"]
            for j in range(0, 12, 2):
                m = idxs[D["j"][idxs] == j]
                if len(m): md.append(f"| {j} | {S_all['retrained MLP'][m].mean():.0f} | {D['X'][m,0].mean():.0f} | {D['X'][m,1].mean():.0f} | {D['X'][m,5].mean():.0f} | {(S_all['retrained MLP'][m] >= thr_all['retrained MLP']).mean()*100:.0f}% |")
            md += [""]
            continue
        rel = {}
        lags = {n: [] for n in models}; never = {n: 0 for n in models}; turned = 0
        for b, ii in by.items():
            ii = np.array(ii); pbs = D["pb"][ii]
            hit = np.where(pbs > 0.30)[0]
            if len(hit) == 0 or hit[0] == 0: continue          # became risky from the first loan: nothing to detect
            t0 = hit[0]; turned += 1
            for pos, i in enumerate(ii):
                rel.setdefault(pos - t0, []).append(i)
            for n in models:
                a = S_all[n][ii] >= thr_all[n]
                after = np.where(~a[t0:])[0]
                if len(after): lags[n].append(int(after[0]))
                else: never[n] += 1
        md += [f"### {KT[k]} ({turned} borrowers who turn risky after at least one safe loan)", "",
               "Rows are loans relative to the turn (0 = first loan with real risk above 30%).", "",
               "| loans from turn | n | mean real risk | mean retrained score | mean on-time | mean late ratio | mean recency | approved (retrained) | approved (linear) | approved (scorecard) |",
               "|---|---|---|---|---|---|---|---|---|---|"]
        for o in range(-4, 5):
            if o not in rel: continue
            m = np.array(rel[o])
            md.append(f"| {o:+d} | {len(m)} | {D['pb'][m].mean()*100:.0f}% | {S_all['retrained MLP'][m].mean():.0f} | {D['X'][m,0].mean():.0f} | {D['X'][m,1].mean():.0f} | {D['X'][m,5].mean():.0f} | "
                      f"{(S_all['retrained MLP'][m] >= thr_all['retrained MLP']).mean()*100:.0f}% | {(S_all['fitted linear'][m] >= thr_all['fitted linear']).mean()*100:.0f}% | {(S_all['scorecard'][m] >= thr_all['scorecard']).mean()*100:.0f}% |")
        md += ["", f"Loans after the turn until the scorer first stops approving that borrower (median; borrowers it never stopped approving before they ran out of loans in the window):", "",
               "| scorer | median lag (loans) | never stopped |", "|---|---|---|"]
        for n in models:
            md.append(f"| {n} | {np.median(lags[n]) if lags[n] else float('nan'):.1f} | {never[n]} of {turned} |")
        md += [""]

    # separability
    md += ["## 3. Can the six features separate the loans that are risky? AUC of each scorer (test months)", "",
           "AUC of the score for 'this loan will be on time' on the loans where real risk is high (>30%) versus low (<10%), per type. 0.5 = no information.", "",
           "| type | " + " | ".join(models) + " |", "|---|" + "---|" * len(models)]
    for k in range(7):
        m = Dte["kind"] == k
        hi, lo = m & (Dte["pb"] > 0.30), m & (Dte["pb"] < 0.10)
        if hi.sum() < 20 or lo.sum() < 20:
            md.append(f"| {KT[k]} | (too few high- or low-risk loans: {int(hi.sum())} / {int(lo.sum())}) |" + " |" * (len(models) - 1)); continue
        md.append(f"| {KT[k]} | " + " | ".join(f"{auc(sc_te[n][lo], sc_te[n][hi]):.2f}" for n in models) + " |")
    md += [""]

    # ---------------- zero-history wallets
    z = D["j"] == 0
    md += ["## 4. Wallets with no history at all (their first loan, all types, whole simulated set)", "",
           "Thresholds are the same as above (each scorer approves the top 50% of test loans). A scorer that gives an unknown wallet a high score contradicts "
           "the thin-file policy (starter quota for unscored wallets).", "",
           "| scorer | mean score at first loan | approved | late/default among approved |", "|---|---|---|---|"]
    for n in models:
        ap = z & (S_all[n] >= thr_all[n])
        md.append(f"| {n} | {S_all[n][z].mean():.0f} | {ap.sum() / z.sum() * 100:.0f}% | {(1 - D['y'][ap].mean()) * 100:.0f}% |")
    md += [f"| (all first loans, no filter) | | 100% | {(1 - D['y'][z].mean()) * 100:.0f}% |", ""]

    # ---------------- 5. leakage + novelty checks
    md += ["## 5. Leakage and novelty checks", ""]
    bad = 0; checked = 0
    for b in np.unique(D["bid"])[:1500]:
        ii = np.where(D["bid"] == b)[0]; ii = ii[np.argsort(D["j"][ii])]
        late = [];
        for pos, i in enumerate(ii):
            tot = len(late); c_late = sum(late); c_on = tot - c_late
            streak = 0
            for v in late[::-1]:
                if v: break
                streak += 1
            exp = [min(c_on, 10) * S // 10, (c_late * S // tot) if tot else 0, int((5 - sum(late[-5:])) * S // 5) if late[-5:] else 0]
            got = [D["X"][i, 0], D["X"][i, 1], D["X"][i, 2]]
            bad += int(list(map(int, got)) != list(map(int, exp))) + int(D["X"][i, 5] != min(streak, 10) * S // 10)
            checked += 1
            late.append(D["y"][i] == 0)
    md += [f"- **Look-ahead in features:** recomputed on-time count, late ratio, last-five consistency and streak for {checked} loans "
           f"from only the borrower's earlier outcomes. Mismatches: {bad}. Debt ratio and history age are not functions of any outcome.",
           f"- **Time order:** every test loan is in months 17-23, every training loan in months 0-13. Latest training month {int(Dtr['month'].max())}, "
           f"earliest test month {int(Dte['month'].min())}."]
    tb = set(Dtr["bid"].tolist()); share = np.mean([b in tb for b in Dte["bid"]])
    md += [f"- **Same borrowers in train and test:** {share*100:.0f}% of test loans belong to a borrower who also has training loans (earlier ones). "
           "This is how a temporal split of a live system works (the same wallets keep borrowing), but it means the model has seen "
           "those borrowers' early behaviour, which is not a population-level holdout."]
    # novelty: for section B (types 3 and 6 excluded from training), do training borrowers contain the transitions?
    def rise(mask):
        out = []
        for b in np.unique(D["bid"][mask]):
            ii = np.where((D["bid"] == b) & mask)[0]
            if len(ii) >= 4:
                ii = ii[np.argsort(D["j"][ii])]; out.append(D["pb"][ii][-1] - D["pb"][ii][0])
        o = np.array(out); return (o > 0.30).mean() if len(o) else float("nan"), len(o)
    held = np.isin(D["kind"], [3, 6])
    r_trB = rise(~held); r_teB = rise(held); r_trA = rise(np.ones(len(D["y"]), bool))
    md += [f"- **Is section B's test type novel?** Share of borrowers (4+ loans) whose real risk rises by more than 30 points over their history: "
           f"{r_trB[0]*100:.0f}% of the training borrowers when deteriorating and strategic types are excluded ({r_trB[1]} borrowers), "
           f"{r_teB[0]*100:.0f}% of the held-out types ({r_teB[1]} borrowers). Training without them removes almost all the transitions, "
           "so section B genuinely tests an unseen behaviour pattern. Recovering borrowers (risk falling) remain in training and are the mirror image, not the same pattern.",
           f"- **Section A:** with all seven types in training, the same share is {r_trA[0]*100:.0f}% of all borrowers, so those transitions are represented there.", ""]
    md += [FINDINGS]
    (ROOT / "model/evaluation3.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
