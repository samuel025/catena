"""Can the retrained MLP replace the deployed one when combined with the contract's rules and a thin-file cap?

Read-only experiment. Does not change weights, Solidity, deployment files or train.py's outputs.
Run:  nice -n 19 .venv/bin/python model/evaluate4.py      Writes model/evaluation4.md.

Rules simulated per borrower, loan by loan (same data as evaluate2/3):
  * Existing contract rules: a wallet is unscored (tier 0, starter quota) until its first repayment event, so the
    decision for a borrower's first loan is always tier 0. After that, effective tier = min(model tier, previous tier + 1):
    cuts are immediate, raises climb one tier per scoring event (the contract's one-tier-per-period rule, with every
    loan event treated as a new period, the most permissive reading).
  * Configuration C adds a hard cap outside the network: with fewer than m completed loans the tier stays 0 (starter quota).
    m = 1 is exactly the existing rules, so configuration B is m = 1.
  * Tier limits are the contract's: 4 / 20 / 50 / 100 units. 'Approved' means effective tier >= 1 (unsecured upgrade
    beyond the starter quota). Exposure is the tier limit, assumed fully drawn; a loss is that exposure on a loan that defaulted.
Two operating points, because the deployed cut-offs (307/563/819) put 92% of this data at tier 1 or above, which is too
saturated to compare anything:
  1. Deployed cut-offs: the retrained model's cut-offs are recalibrated on VALIDATION data to give the same raw tier shares
     as the deployed model. 'Approved' = tier >= 1.
  2. Matched quartiles: both models' cut-offs are set on validation so that scored loans split 25/25/25/25 across tiers 0-3.
     'Approved' = tier >= 2 (a limit of 50 units or more).
Selection protocol (nothing is tuned on the test set): m is chosen on validation as the m with the lowest loss per loan among
those whose false-rejection rate is at most 5 points above configuration B's. The test set (months 17-23) is then evaluated once.
"""
import json
import pathlib
import numpy as np
import train as T
import evaluate2 as E

ROOT = pathlib.Path(__file__).resolve().parent.parent
S = T.S
LIMIT = np.array([4.0, 20.0, 50.0, 100.0])
KT = E.TYPES
MS = [1, 2, 3, 4, 5, 6]


FINDINGS = "# What the evidence says\n\n- **The thin-file cap does not earn its place.** Each extra required loan removes risky approvals, but it removes reliable borrowers just as fast. In the validation sweeps, shifting the retrained model's plain cut-offs to the same approval rate beats the cap on risky approvals or false rejections (operating point 2, m = 3: cap 11.1% risky approved and 62.0% false rejection, plain shift 10.9% and 55.7%; operating point 1: cap 64.4% risky approved, plain shift 34.1%). The protocol therefore picks m = 1, which is the existing contract rule, so configuration C is the same as B. The contract's first-decision-is-the-starter-quota rule already does the work a zero-loan cap would.\n- **The retrained model's gain survives, and does not come from the cap.** At operating point 2 (approved = tier 2 or above), B approves 13.0% of truly risky loans against 28.9% for A (24.6% for A with cut-offs shifted to a nearer approval rate), and loses 5.06% per unit of exposure against 6.00% (5.88% shifted). On deteriorating borrowers, risky loans approved fall from 42.2% to 15.6%; on strategic defaulters, from 32.5% to 15.5%.\n- **The price is more good borrowers turned away and a weaker thin-file record.** False rejection is 37.9% against 33.2% for A at a nearer approval rate, and reliable loans get an average limit of 55.9 against 58.3. The retrained model also approves more wallets with only two completed loans (67.3% against 41.3%), and those approved are late more often (11.2% against 7.5%). On recovering borrowers, late among approved is 29.8% against 17.9%. So the thin-file weakness is real, but it sits at one or two completed loans and is better handled by where the cut-offs sit than by a cap.\n- **The retrained model only works with new tier cut-offs.** It outputs P(on time), so its tier cut-offs (here 739 / 831 / 899) differ from the deployed 307 / 563 / 819, and they were set on validation data. At the deployed cut-offs the data is saturated (about 88% approved at tier 1 or above, rows labelled operating point 1), so that comparison says little.\n- **Limits of all of this.** The simulator, the borrower types and the labels are ours, the retrained model is trained on exactly those behaviours, and the loss model assumes a fully drawn tier limit. A gain here is a gain at recovering behaviours we invented. It is not evidence about real borrowers.\n"


def raw_tiers(score, cuts):
    return (score[:, None] >= np.asarray(cuts)[None, :]).sum(1)


def effective(D, raw, m):
    """Existing rules plus an optional cap: tier 0 until m completed loans, then one tier per event, cuts immediate."""
    eff = np.zeros(len(raw), dtype=np.int64)
    prev_b = -1; prev = 0
    for i in range(len(raw)):
        if D["bid"][i] != prev_b:
            prev_b = D["bid"][i]; prev = 0
        n = D["j"][i]                       # completed loans before this one
        t = 0 if n < max(m, 1) else min(int(raw[i]), prev + 1)
        eff[i] = t; prev = t
    return eff


def metrics(D, eff, ap_tier=1):
    ap = eff >= ap_tier
    risky = D["pb"] > 0.30; good = D["pb"] < 0.10
    expo = LIMIT[eff]
    n = len(eff)
    return {
        "approval": float(ap.mean()),
        "risky_approved": float(ap[risky].mean()) if risky.any() else float("nan"),
        "late_among_approved": float(1 - D["y"][ap].mean()) if ap.any() else float("nan"),
        "false_rejection": float((~ap)[good].mean()) if good.any() else float("nan"),
        "loss_per_loan": float((expo * D["dflt"]).sum() / n),
        "exposure_per_loan": float(expo.mean()),
        "loss_rate": float((expo * D["dflt"]).sum() / expo.sum()),
        "good_exposure": float(expo[good].mean()) if good.any() else float("nan"),
    }


def pct(x):
    return "-" if x != x else f"{x*100:.1f}%"


def match_offset(D, s, cuts, target, mask, ap_tier):
    """Offset added to a model's scores so that its approval rate (existing rules, m = 1) on `mask` equals `target`. Validation only."""
    lo, hi = -600.0, 600.0
    for _ in range(30):
        mid = (lo + hi) / 2
        a = metrics(E.sub(D, mask), effective(D, raw_tiers(s.astype(np.float64) + mid, cuts), 1)[mask], ap_tier)["approval"]
        if a > target: hi = mid
        else: lo = mid
    return (lo + hi) / 2


def operating_point(D, masks, s_dep, s_new, title, dep_cuts, new_cuts, ap_tier):
    tr, va, te = masks
    raw_dep = raw_tiers(s_dep.astype(np.float64), dep_cuts); raw_new = raw_tiers(s_new.astype(np.float64), new_cuts)

    def run(raw, m, mask):
        eff = effective(D, raw, m)
        return metrics(E.sub(D, mask), eff[mask], ap_tier), eff

    md = [f"# {title}", "",
          f"Cut-offs: deployed model {', '.join(f'{c:.0f}' for c in dep_cuts)}; retrained model {', '.join(f'{c:.0f}' for c in new_cuts)}. Approved = tier >= {ap_tier}.", "",
          "## Validation sweep (months 14-16): choosing m", "",
          "| config | approval | risky approved | late among approved | false rejection | loss per loan | exposure per loan | B with plain cut-offs shifted to the same approval: risky approved / false rejection / loss per loan |", "|---|---|---|---|---|---|---|---|"]
    A_v, _ = run(raw_dep, 1, va)
    md.append(f"| A deployed + rules | {pct(A_v['approval'])} | {pct(A_v['risky_approved'])} | {pct(A_v['late_among_approved'])} | {pct(A_v['false_rejection'])} | {A_v['loss_per_loan']:.2f} | {A_v['exposure_per_loan']:.1f} | |")
    cand = {}
    for m in MS:
        r, _ = run(raw_new, m, va); cand[m] = r
        if m == 1: cmp_ = "(same as the row)"
        else:
            o = match_offset(D, s_new, new_cuts, r["approval"], va, ap_tier)
            x = run(raw_tiers(s_new.astype(np.float64) + o, new_cuts), 1, va)[0]
            cmp_ = f"{pct(x['risky_approved'])} / {pct(x['false_rejection'])} / {x['loss_per_loan']:.2f}"
        md.append(f"| retrained, m = {m}{' (= B)' if m == 1 else ''} | {pct(r['approval'])} | {pct(r['risky_approved'])} | {pct(r['late_among_approved'])} | {pct(r['false_rejection'])} | {r['loss_per_loan']:.2f} | {r['exposure_per_loan']:.1f} | {cmp_} |")
    ok = [m for m in MS if cand[m]["false_rejection"] <= cand[1]["false_rejection"] + 0.05]
    m_star = min(ok, key=lambda m: cand[m]["loss_per_loan"])
    md += ["", f"Rule: lowest loss per loan with false rejection at most 5 points above B's ({pct(cand[1]['false_rejection'])}). Chosen on validation: **m = {m_star}**.", ""]

    configs = [("A: deployed + rules", raw_dep, 1), ("B: retrained + rules", raw_new, 1)]
    if m_star > 1:
        target = cand[m_star]["approval"]; lo, hi = -400.0, 400.0   # B shifted to C's approval rate, offset found on validation only
        for _ in range(40):
            mid = (lo + hi) / 2
            a = run(raw_tiers(s_new.astype(np.float64) + mid, new_cuts), 1, va)[0]["approval"]
            if a > target: hi = mid
            else: lo = mid
        configs.append(("B': retrained + rules, shifted to C's approval rate", raw_tiers(s_new.astype(np.float64) + (lo + hi) / 2, new_cuts), 1))
    configs.append((f"C: retrained + thin-file cap (m = {m_star})", raw_new, m_star))
    tgt_ap = run(raw_new, 1, va)[0]["approval"]
    if abs(A_v["approval"] - tgt_ap) > 0.02:   # compare A at B's approval rate (offset found on validation)
        oa = match_offset(D, s_dep, dep_cuts, tgt_ap, va, ap_tier)
        configs.insert(1, ("A': deployed, cut-offs shifted to B's approval rate", raw_tiers(s_dep.astype(np.float64) + oa, dep_cuts), 1))
    res = {}; effs = {}
    for name, raw, m in configs:
        res[name], effs[name] = run(raw, m, te)
    md += ["## Test set (months 17-23), evaluated once", "",
           "| config | actual approval | risky approved | late among approved | false rejection | loss per loan | exposure per loan | loss per unit exposure | exposure to reliable loans |", "|---|---|---|---|---|---|---|---|---|"]
    for name, _, _ in configs:
        r = res[name]
        md.append(f"| {name} | {pct(r['approval'])} | {pct(r['risky_approved'])} | {pct(r['late_among_approved'])} | {pct(r['false_rejection'])} | {r['loss_per_loan']:.2f} | {r['exposure_per_loan']:.1f} | {r['loss_rate']*100:.2f}% | {r['good_exposure']:.1f} |")
    md += ["", "Exposure to reliable loans = average limit granted on loans whose real risk is below 10% (higher = reliable borrowers get more credit).", "",
           "## By borrower type (test): risky approved / late among approved / loss per loan", "",
           "| type | truly risky loans | " + " | ".join(n for n, _, _ in configs) + " |", "|---|---|" + "---|" * len(configs)]
    for k in range(7):
        m = te & (D["kind"] == k)
        if not m.any(): continue
        Dk = E.sub(D, m); risky = int((Dk["pb"] > 0.3).sum()); cells = []
        for name, _, _ in configs:
            r = metrics(Dk, effs[name][m], ap_tier)
            cells.append(("no risky loans" if not risky else pct(r["risky_approved"])) + f" / {pct(r['late_among_approved'])} / {r['loss_per_loan']:.2f}")
        md.append(f"| {KT[k]} | {risky} | " + " | ".join(cells) + " |")
    md += ["", "## Early loans (test): approval of wallets with 0, 1 or 2 completed loans", "",
           "| config | n = 0 | n = 1 | late among approved | n = 2 | late among approved |", "|---|---|---|---|---|---|"]
    for name, _, _ in configs:
        eff = effs[name]; row = [name]
        for n in (0, 1, 2):
            mk = te & (D["j"] == n); ap = mk & (eff >= ap_tier)
            row.append(pct(float(ap.sum() / mk.sum())))
            if n: row.append(pct(float(1 - D["y"][ap].mean())) if ap.any() else "-")
        md.append("| " + " | ".join(row) + " |")
    return md + [""]


def main(epochs=60):
    rng = np.random.default_rng(2026)
    D = E.simulate_loans(9000, rng)
    tr, va, te = D["month"] < 14, (D["month"] >= 14) & (D["month"] < 17), D["month"] >= 17
    Dtr, Dva = E.sub(D, tr), E.sub(D, va)
    w = json.load(open(ROOT / "model/weights.json"))
    q_ship = (np.array(w["W1"]), np.array(w["b1"]), np.array(w["W2"]), w["b2"])
    q_new = E.fit_weighted(Dtr, Dva, 1.0, epochs)
    s_dep = T.int_forward(D["X"], q_ship); s_new = T.int_forward(D["X"], q_new)
    scored = D["j"] >= 1
    vs = va & scored
    dep_deployed = [307.0, 563.0, 819.0]
    shares = [float((s_dep[vs] < c).mean()) for c in dep_deployed]
    new_matched = [float(np.quantile(s_new[vs], sh)) for sh in shares]
    quart = [0.25, 0.5, 0.75]
    md = ["# Evaluation 4: can the retrained MLP replace the deployed one with a thin-file cap?", "",
          "Read-only experiment (`model/evaluate4.py`, seeded). Nothing about the deployed model, contracts or training was changed. "
          "Synthetic data. A = deployed MLP with the contract's rules; B = retrained MLP with the same rules; C = B plus a hard cap "
          "(tier 0 until m completed loans). Rules, operating points and the selection protocol are described at the top of the script.", ""]
    md += operating_point(D, (tr, va, te), s_dep, s_new, "Operating point 1: deployed cut-offs, approved = tier >= 1", dep_deployed, new_matched, 1)
    md += operating_point(D, (tr, va, te), s_dep, s_new, "Operating point 2: matched quartiles, approved = tier >= 2",
                          [float(np.quantile(s_dep[vs], q)) for q in quart], [float(np.quantile(s_new[vs], q)) for q in quart], 2)
    md += ["# Correction to evaluation 3", "",
           "`evaluate3.py` scored first loans (zero history) with the raw network and found the retrained model gives them a top score. "
           "The live system never does that: a wallet is unscored until its first repayment event, so its first decision is always the starter quota, "
           "and the contract then raises one tier per period. The n = 0 columns above show this. The thin-file risk that remains is for wallets with one or two completed loans.", ""]
    md += [FINDINGS]
    (ROOT / "model/evaluation4.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
