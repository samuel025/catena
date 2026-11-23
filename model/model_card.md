# Catena model card

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
| MLP (integer, on-chain) | 0.0188 | 0.6665 | 0.1428 | 0.0037 |
| MLP (float, reference) | 0.0188 | 0.6660 | 0.1457 | 0.0042 |
| Plain formula (hand-set weights) | 0.0411 | 0.4673 | 0.4253 | 0.0505 |
| Linear formula fitted on the training data | 0.0198 | 0.6590 | 0.1548 | 0.0025 |

Over-lending = predicted tier above the true tier. Severe = two or more tiers above.

## Properties
- Monotone violations in 20,000 random trials (raise one feature, check score): **0**.
- Max |integer score - float score| on test: 2.5 (of 1024).
- Monotonicity is per feature at the input level. It is guaranteed by sign-constrained weights, ReLU, floor rounding
  and saturation; fuzz tests are a backstop.
- Solidity parity: `test/Mlp.t.sol` checks `Mlp.score` against `model/vectors.json` (corners and random inputs).

## Limits
Synthetic data; thresholds are illustrative; address-based identity means a defaulter can start a new wallet at tier 0.
If the plain formula matches or beats the MLP in the table above, that is a real finding: the network is here because
the track asks for an on-chain model, and the formula is the honest comparison.
