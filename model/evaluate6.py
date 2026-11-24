"""Does recent repayment behaviour add information beyond lifetime history? Python only, read-only.

Run:  nice -n 19 .venv/bin/python model/evaluate6.py      Writes model/evaluation6.md.
Does not change deployed weights, train.py outputs, Solidity or deployment files.

Candidates (all keep the monotone sign constraints, trained on months 0-13, validated on 14-16, tested once on 17-23):
  A  existing six features (retrained on this data)
  B  six + recent late ratio over the last w completed loans (sign -1: more recent late payments never raise the score)
  C  B + recent trend = 0.5 + (late ratio of the w loans before the window - recent late ratio) / 2  (sign +1, 0.5 = no change / not enough history)
  w in {3, 5, 10}. A "D: stronger lifetime-history influence" variant from the proposal is not run: it has no definition that
  is not just another weight setting, and the same network already learns that weight.
Every feature uses only loans completed before the loan being decided (prefix sums per borrower).
Operating point as in evaluation 4 (cut-offs are validation quartiles per model, approved = tier >= 2 after the contract's
one-tier-per-event rule). Selection rule, validation only: among candidates whose deteriorating-borrower risky approvals are
at most 2 points above A's, take the one that approves the most low-risk recovering loans. Three training seeds per candidate.
"""
import json
import pathlib
import numpy as np
import train as T
import evaluate2 as E
import evaluate4 as F

ROOT = pathlib.Path(__file__).resolve().parent.parent
S = T.S
SEEDS = (1, 2, 3)


def extra_features(D, w):
    n = len(D["y"]); rec = np.zeros(n, dtype=np.int64); trend = np.full(n, S // 2, dtype=np.int64)
    late = (D["y"] == 0).astype(np.int64)
    _, starts = np.unique(D["bid"], return_index=True); starts = list(starts) + [n]
    for a, b in zip(starts[:-1], starts[1:]):
        cs = np.concatenate([[0], np.cumsum(late[a:b])])        # cs[j] = late count among this borrower's loans before loan j
        for j in range(b - a):
            if j == 0: continue
            lo = max(0, j - w); r = (cs[j] - cs[lo]) / (j - lo)
            rec[a + j] = int(round(r * S))
            p0, p1 = max(0, j - 2 * w), lo
            if p1 > p0:
                pv = (cs[p1] - cs[p0]) / (p1 - p0)
                trend[a + j] = int(np.clip(round((0.5 + (pv - r) / 2) * S), 0, S))
    return rec, trend


def project(W1, W2, sign):
    for i in range(len(sign)):
        W1[:, i] = np.maximum(W1[:, i] * sign[i], 0) * sign[i]
    np.maximum(W2, 0, out=W2)


def train_n(X, y, Xv, yv, sign, seed, epochs=60, lr=0.01, H=8):
    """Same network and optimiser as train.train, for any number of inputs."""
    rng = np.random.default_rng(seed); nf = X.shape[1]
    x = X / S; xv = Xv / S
    W1 = rng.normal(0, 0.3, (H, nf)); project(W1, np.zeros(H), sign)
    b1 = rng.normal(0.1, 0.1, H); W2 = np.abs(rng.normal(0.3, 0.1, H)); b2 = np.array([0.0])
    params = [W1, b1, W2, b2]; m = [np.zeros_like(p) for p in params]; v = [np.zeros_like(p) for p in params]
    best, best_p = 1e9, None; n = len(x); bs = 512
    for ep in range(epochs):
        perm = rng.permutation(n)
        for s0 in range(0, n, bs):
            idx = perm[s0:s0 + bs]; xb = x[idx]; yb = y[idx]
            z = xb @ W1.T + b1; h = np.maximum(z, 0); out = h @ W2 + b2[0]
            g = 2 * (out - yb) / len(idx)
            gW2 = h.T @ g; gb2 = np.array([g.sum()]); gh = np.outer(g, W2) * (z > 0)
            grads = [gh.T @ xb, gh.sum(0), gW2, gb2]
            t = ep * (n // bs + 1) + s0 // bs + 1
            for j, (p, gr) in enumerate(zip(params, grads)):
                m[j] = 0.9 * m[j] + 0.1 * gr; v[j] = 0.999 * v[j] + 0.001 * gr * gr
                p -= lr * (m[j] / (1 - 0.9 ** t)) / (np.sqrt(v[j] / (1 - 0.999 ** t)) + 1e-8)
            project(W1, W2, sign)
        if ep % 10 == 0 or ep == epochs - 1:
            ov = np.maximum(xv @ W1.T + b1, 0) @ W2 + b2[0]
            mse = float(np.mean((np.clip(ov, 0, 1) - yv) ** 2))
            if mse < best: best = mse; best_p = [p.copy() for p in params]
    return T.quantize(best_p)


def monotone_violations(q, sign, trials=5000):
    rng = np.random.default_rng(3); bad = 0; nf = len(sign)
    for _ in range(trials):
        x = rng.integers(0, S + 1, nf); i = int(rng.integers(0, nf)); x2 = x.copy(); x2[i] = rng.integers(x[i], S + 1)
        a = int(T.int_forward(x[None], q)[0]); b = int(T.int_forward(x2[None], q)[0])
        bad += int((sign[i] > 0 and b < a) or (sign[i] < 0 and b > a))
    return bad


def evaluate(D, s, mask_va, mask_eval):
    """Operating point as in evaluation 4: validation-quartile cut-offs, existing rules, approved = tier >= 2."""
    vs = mask_va & (D["j"] >= 1)
    cuts = [float(np.quantile(s[vs], q)) for q in (0.25, 0.5, 0.75)]
    eff = F.effective(D, F.raw_tiers(s.astype(np.float64), cuts), 1)
    out = {}
    def sel(mk):
        Dk = E.sub(D, mk); ap = eff[mk] >= 2
        r = F.metrics(Dk, eff[mk], 2)
        r["precision"] = float(Dk["y"][ap].mean()) if ap.any() else float("nan")
        r["recall"] = float(ap[Dk["y"] == 1].mean()) if (Dk["y"] == 1).any() else float("nan")
        return r
    out["all"] = sel(mask_eval)
    for k in range(7):
        out[k] = sel(mask_eval & (D["kind"] == k))
    rec = mask_eval & (D["kind"] == 5) & (D["pb"] < 0.30)
    out["recov_lowrisk_approved"] = float((eff[rec] >= 2).mean())
    return out, eff


def avg(rs, f):
    return float(np.mean([f(r) for r in rs]))


def main():
    rng = np.random.default_rng(2026)
    D = E.simulate_loans(9000, rng)
    tr, va, te = D["month"] < 14, (D["month"] >= 14) & (D["month"] < 17), D["month"] >= 17
    base_sign = np.array([+1, -1, +1, -1, +1, +1])
    feats = {}
    for w in (3, 5, 10):
        rec, trd = extra_features(D, w)
        feats[w] = (rec, trd)
    cands = [("A  six features", None, None)]
    for w in (3, 5, 10):
        cands.append((f"B  + recent late ratio (w={w})", w, "B"))
    for w in (3, 5, 10):
        cands.append((f"C  + recent ratio + trend (w={w})", w, "C"))

    def build(w, kind):
        if kind is None: return D["X"], base_sign
        rec, trd = feats[w]
        if kind == "B": return np.hstack([D["X"], rec[:, None]]), np.append(base_sign, -1)
        return np.hstack([D["X"], rec[:, None], trd[:, None]]), np.append(base_sign, [-1, +1])

    results = {}
    for name, w, kind in cands:
        X, sign = build(w, kind)
        runs = []
        for sd in SEEDS:
            q = train_n(X[tr], D["y"][tr], X[va], D["y"][va], sign, sd)
            s = T.int_forward(X, q)
            rv, _ = evaluate(D, s, va, va); rt, _ = evaluate(D, s, va, te)
            runs.append({"q": q, "val": rv, "test": rt, "mono": monotone_violations(q, sign, 2000) if sd == 1 else None, "s": s})
        results[name] = runs
    # deployed and reference
    w0 = json.load(open(ROOT / "model/weights.json"))
    q_dep = (np.array(w0["W1"]), np.array(w0["b1"]), np.array(w0["W2"]), w0["b2"])
    s_dep = T.int_forward(D["X"], q_dep)
    dep_v, _ = evaluate(D, s_dep, va, va); dep_t, _ = evaluate(D, s_dep, va, te)

    md = ["# Evaluation 6: does recent repayment behaviour add information?", "",
          "Python only (`model/evaluate6.py`, seeded). Synthetic data; nothing deployed or changed. Method and selection rule are in the script's header.", "",
          "## Validation (months 14-16): all candidates, mean of 3 training seeds", "",
          "Approved = tier 2 or above. 'Recovering low-risk approved' = share of recovering borrowers' loans with real risk under 30% that get tier 2 or above. Risky approved = loans with real risk over 30%.", "",
          "| candidate | overall risky approved | false rejection | loss per loan | recovering low-risk approved | deteriorating risky approved | strategic risky approved | consistent late among approved |",
          "|---|---|---|---|---|---|---|---|"]
    def row(name, rs):
        g = lambda f: avg(rs, f)
        return (f"| {name} | {g(lambda r: r['all']['risky_approved'])*100:.1f}% | {g(lambda r: r['all']['false_rejection'])*100:.1f}% | {g(lambda r: r['all']['loss_per_loan']):.2f} | "
                f"{g(lambda r: r['recov_lowrisk_approved'])*100:.1f}% | {g(lambda r: r[3]['risky_approved'])*100:.1f}% | {g(lambda r: r[6]['risky_approved'])*100:.1f}% | {g(lambda r: r[0]['late_among_approved'])*100:.1f}% |")
    md.append(row("deployed model", [dep_v]))
    for name, _, _ in cands:
        md.append(row(name, [r["val"] for r in results[name]]))
    base_det = avg([r["val"] for r in results[cands[0][0]]], lambda r: r[3]["risky_approved"])
    ok = [c for c in cands[1:] if avg([r["val"] for r in results[c[0]]], lambda r: r[3]["risky_approved"]) <= base_det + 0.02]
    A_name = cands[0][0]
    sel = max(ok, key=lambda c: avg([r["val"] for r in results[c[0]]], lambda r: r["recov_lowrisk_approved"])) if ok else None
    md += ["", f"Selection rule (validation only): deteriorating risky approvals must stay within 2 points of A ({base_det*100:.1f}%); then most low-risk recovering loans approved. "
           + (f"Chosen: **{sel[0]}**." if sel else "No candidate qualified: keep the six-feature model."), ""]
    cmp = [("deployed model", [dep_t]), (A_name + " (retrained)", [r["test"] for r in results[A_name]])]
    if sel: cmp.append((sel[0] + " (selected)", [r["test"] for r in results[sel[0]]]))
    md += ["## Test (months 17-23), evaluated once, mean of 3 seeds (range of the selected model in the next table)", "",
           "| model | overall risky approved | false rejection | precision | recall | loss per loan | recovering low-risk approved | deteriorating risky approved | strategic risky approved |", "|---|---|---|---|---|---|---|---|---|"]
    for name, rs in cmp:
        g = lambda f: avg(rs, f)
        md.append(f"| {name} | {g(lambda r: r['all']['risky_approved'])*100:.1f}% | {g(lambda r: r['all']['false_rejection'])*100:.1f}% | {g(lambda r: r['all']['precision'])*100:.1f}% | {g(lambda r: r['all']['recall'])*100:.1f}% | "
                  f"{g(lambda r: r['all']['loss_per_loan']):.2f} | {g(lambda r: r['recov_lowrisk_approved'])*100:.1f}% | {g(lambda r: r[3]['risky_approved'])*100:.1f}% | {g(lambda r: r[6]['risky_approved'])*100:.1f}% |")
    md += ["", "## Test by borrower type: risky approved / late among approved / loss per loan", "",
           "| type | " + " | ".join(n for n, _ in cmp) + " |", "|---|" + "---|" * len(cmp)]
    for k in range(7):
        cells = []
        for name, rs in cmp:
            ra = avg(rs, lambda r: r[k]["risky_approved"]); la = avg(rs, lambda r: r[k]["late_among_approved"]); lo = avg(rs, lambda r: r[k]["loss_per_loan"])
            cells.append(("no risky loans" if ra != ra else f"{ra*100:.1f}%") + f" / {la*100:.1f}% / {lo:.2f}")
        md.append(f"| {E.TYPES[k]} | " + " | ".join(cells) + " |")
    if sel:
        runs = results[sel[0]]
        rng_ = lambda f: f"{min(f(r['test']) for r in runs)*100:.1f}% to {max(f(r['test']) for r in runs)*100:.1f}%"
        runsA = results[A_name]; rngA = lambda f: f"{min(f(r['test']) for r in runsA)*100:.1f}% to {max(f(r['test']) for r in runsA)*100:.1f}%"
        md += ["", "## Seed spread on the test set (selected vs six-feature)", "",
               "| metric | selected | six features |", "|---|---|---|",
               f"| recovering low-risk approved | {rng_(lambda r: r['recov_lowrisk_approved'])} | {rngA(lambda r: r['recov_lowrisk_approved'])} |",
               f"| deteriorating risky approved | {rng_(lambda r: r[3]['risky_approved'])} | {rngA(lambda r: r[3]['risky_approved'])} |",
               f"| strategic risky approved | {rng_(lambda r: r[6]['risky_approved'])} | {rngA(lambda r: r[6]['risky_approved'])} |", ""]
        # calibration
        m = te & (D["j"] >= 1); s = results[sel[0]][0]["s"]; p = s[m] / S; y = D["y"][m]
        md += ["## Calibration of the selected model (simulated data only)", "",
               "| predicted bin | loans | mean predicted | observed on-time |", "|---|---|---|---|"]
        gaps = 0
        for a, b in zip([0, .5, .7, .8, .85, .9, .95], [.5, .7, .8, .85, .9, .95, 1.01]):
            k = (p >= a) & (p < b)
            if k.sum() >= 30: md.append(f"| {a:.2f}-{min(b,1):.2f} | {int(k.sum())} | {p[k].mean():.3f} | {y[k].mean():.3f} |"); gaps += abs(p[k].mean() - y[k].mean()) * k.sum()
        md += ["", f"Expected calibration error {gaps/len(p):.3f}. This describes the simulator's own outcomes, not real borrowers.", ""]
    md += ["## Monotone check (integer weights, seed 1, 2000 random trials)", ""]
    for name, _, _ in cands:
        md.append(f"- {name}: {results[name][0]['mono']} violations")
    md.append("")
    (ROOT / "model/evaluation6.md").write_text("\n".join(md)); print("\n".join(md))


if __name__ == "__main__":
    main()
