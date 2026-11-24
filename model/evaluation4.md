# Evaluation 4: can the retrained MLP replace the deployed one with a thin-file cap?

Read-only experiment (`model/evaluate4.py`, seeded). Nothing about the deployed model, contracts or training was changed. Synthetic data. A = deployed MLP with the contract's rules; B = retrained MLP with the same rules; C = B plus a hard cap (tier 0 until m completed loans). Rules, operating points and the selection protocol are described at the top of the script.

# Operating point 1: deployed cut-offs, approved = tier >= 1

Cut-offs: deployed model 307, 563, 819; retrained model 705, 758, 941. Approved = tier >= 1.

## Validation sweep (months 14-16): choosing m

| config | approval | risky approved | late among approved | false rejection | loss per loan | exposure per loan | B with plain cut-offs shifted to the same approval: risky approved / false rejection / loss per loan |
|---|---|---|---|---|---|---|---|
| A deployed + rules | 82.0% | 74.1% | 19.1% | 15.2% | 2.25 | 34.2 | |
| retrained, m = 1 (= B) | 82.6% | 73.6% | 18.8% | 15.3% | 1.98 | 33.4 | (same as the row) |
| retrained, m = 2 | 73.5% | 70.4% | 19.6% | 27.4% | 1.87 | 29.5 | 53.7% / 16.9% / 1.59 |
| retrained, m = 3 | 63.7% | 64.4% | 20.5% | 38.2% | 1.72 | 25.8 | 34.1% / 21.1% / 1.32 |
| retrained, m = 4 | 54.7% | 58.8% | 21.1% | 47.4% | 1.56 | 22.6 | 23.2% / 26.1% / 1.15 |
| retrained, m = 5 | 46.0% | 51.3% | 21.6% | 55.8% | 1.39 | 19.6 | 18.8% / 31.5% / 0.89 |
| retrained, m = 6 | 38.4% | 45.0% | 22.0% | 63.8% | 1.20 | 16.7 | 16.2% / 34.0% / 0.68 |

Rule: lowest loss per loan with false rejection at most 5 points above B's (15.3%). Chosen on validation: **m = 1**.

## Test set (months 17-23), evaluated once

| config | actual approval | risky approved | late among approved | false rejection | loss per loan | exposure per loan | loss per unit exposure | exposure to reliable loans |
|---|---|---|---|---|---|---|---|---|
| A: deployed + rules | 88.4% | 81.7% | 20.2% | 7.6% | 2.65 | 38.3 | 6.93% | 49.2 |
| B: retrained + rules | 88.6% | 79.2% | 19.9% | 7.7% | 2.20 | 35.8 | 6.14% | 46.6 |
| C: retrained + thin-file cap (m = 1) | 88.6% | 79.2% | 19.9% | 7.7% | 2.20 | 35.8 | 6.14% | 46.6 |

Exposure to reliable loans = average limit granted on loans whose real risk is below 10% (higher = reliable borrowers get more credit).

## By borrower type (test): risky approved / late among approved / loss per loan

| type | truly risky loans | A: deployed + rules | B: retrained + rules | C: retrained + thin-file cap (m = 1) |
|---|---|---|---|---|
| consistent | 0 | no risky loans / 5.1% / 0.54 | no risky loans / 5.1% / 0.52 | no risky loans / 5.1% / 0.52 |
| new / thin file | 0 | no risky loans / 12.0% / 0.72 | no risky loans / 12.2% / 0.79 | no risky loans / 12.2% / 0.79 |
| occasional late | 0 | no risky loans / 14.9% / 1.41 | no risky loans / 15.1% / 1.24 | no risky loans / 15.1% / 1.24 |
| deteriorating | 2268 | 95.2% / 35.7% / 3.28 | 94.7% / 35.5% / 2.72 | 94.7% / 35.5% / 2.72 |
| over-leveraged | 0 | no risky loans / 14.7% / 1.05 | no risky loans / 14.9% / 1.27 | no risky loans / 14.9% / 1.27 |
| recovering | 1554 | 51.9% / 25.7% / 1.25 | 52.8% / 26.5% / 1.17 | 52.8% / 26.5% / 1.17 |
| strategic defaulter | 1854 | 90.2% / 51.9% / 12.80 | 82.6% / 50.1% / 9.70 | 82.6% / 50.1% / 9.70 |

## Early loans (test): approval of wallets with 0, 1 or 2 completed loans

| config | n = 0 | n = 1 | late among approved | n = 2 | late among approved |
|---|---|---|---|---|---|
| A: deployed + rules | 0.0% | 85.8% | 11.5% | 87.9% | 13.7% |
| B: retrained + rules | 0.0% | 85.8% | 11.5% | 95.8% | 14.5% |
| C: retrained + thin-file cap (m = 1) | 0.0% | 85.8% | 11.5% | 95.8% | 14.5% |

# Operating point 2: matched quartiles, approved = tier >= 2

Cut-offs: deployed model 494, 608, 696; retrained model 739, 831, 899. Approved = tier >= 2.

## Validation sweep (months 14-16): choosing m

| config | approval | risky approved | late among approved | false rejection | loss per loan | exposure per loan | B with plain cut-offs shifted to the same approval: risky approved / false rejection / loss per loan |
|---|---|---|---|---|---|---|---|
| A deployed + rules | 41.3% | 26.4% | 14.4% | 39.5% | 2.25 | 38.1 | |
| retrained, m = 1 (= B) | 36.5% | 15.5% | 12.0% | 43.8% | 1.63 | 34.3 | (same as the row) |
| retrained, m = 2 | 29.5% | 13.3% | 12.5% | 53.8% | 1.52 | 29.4 | 12.8% / 47.6% / 1.07 |
| retrained, m = 3 | 23.6% | 11.1% | 12.0% | 62.0% | 1.36 | 25.3 | 10.9% / 55.7% / 0.86 |
| retrained, m = 4 | 18.8% | 8.9% | 11.6% | 68.6% | 1.22 | 21.7 | 8.7% / 63.7% / 0.77 |
| retrained, m = 5 | 14.7% | 7.0% | 11.4% | 74.9% | 1.04 | 18.3 | 7.3% / 71.0% / 0.72 |
| retrained, m = 6 | 11.2% | 4.9% | 10.5% | 80.4% | 0.86 | 15.2 | 5.8% / 76.9% / 0.68 |

Rule: lowest loss per loan with false rejection at most 5 points above B's (43.8%). Chosen on validation: **m = 1**.

## Test set (months 17-23), evaluated once

| config | actual approval | risky approved | late among approved | false rejection | loss per loan | exposure per loan | loss per unit exposure | exposure to reliable loans |
|---|---|---|---|---|---|---|---|---|
| A: deployed + rules | 47.4% | 28.9% | 14.7% | 28.2% | 2.57 | 42.9 | 6.00% | 63.6 |
| A': deployed, cut-offs shifted to B's approval rate | 41.9% | 24.6% | 13.8% | 33.2% | 2.24 | 38.0 | 5.88% | 58.3 |
| B: retrained + rules | 37.0% | 13.0% | 11.8% | 37.9% | 1.80 | 35.6 | 5.06% | 55.9 |
| C: retrained + thin-file cap (m = 1) | 37.0% | 13.0% | 11.8% | 37.9% | 1.80 | 35.6 | 5.06% | 55.9 |

Exposure to reliable loans = average limit granted on loans whose real risk is below 10% (higher = reliable borrowers get more credit).

## By borrower type (test): risky approved / late among approved / loss per loan

| type | truly risky loans | A: deployed + rules | A': deployed, cut-offs shifted to B's approval rate | B: retrained + rules | C: retrained + thin-file cap (m = 1) |
|---|---|---|---|---|---|
| consistent | 0 | no risky loans / 4.1% / 0.65 | no risky loans / 3.8% / 0.57 | no risky loans / 4.0% / 0.51 | no risky loans / 4.0% / 0.51 |
| new / thin file | 0 | no risky loans / 8.2% / 0.67 | no risky loans / 5.1% / 0.57 | no risky loans / 12.4% / 0.77 | no risky loans / 12.4% / 0.77 |
| occasional late | 0 | no risky loans / 12.7% / 1.53 | no risky loans / 11.9% / 1.40 | no risky loans / 13.5% / 1.18 | no risky loans / 13.5% / 1.18 |
| deteriorating | 2268 | 42.2% / 34.0% / 3.48 | 36.6% / 33.9% / 3.08 | 15.6% / 28.7% / 2.41 | 15.6% / 28.7% / 2.41 |
| over-leveraged | 0 | no risky loans / 13.3% / 0.92 | no risky loans / 13.5% / 0.75 | no risky loans / 13.3% / 0.81 | no risky loans / 13.3% / 0.81 |
| recovering | 1554 | 5.3% / 17.9% / 0.91 | 3.3% / 16.5% / 0.77 | 6.4% / 29.8% / 0.67 | 6.4% / 29.8% / 0.67 |
| strategic defaulter | 1854 | 32.5% / 38.8% / 11.94 | 27.9% / 38.4% / 10.27 | 15.5% / 24.6% / 7.80 | 15.5% / 24.6% / 7.80 |

## Early loans (test): approval of wallets with 0, 1 or 2 completed loans

| config | n = 0 | n = 1 | late among approved | n = 2 | late among approved |
|---|---|---|---|---|---|
| A: deployed + rules | 0.0% | 0.0% | - | 41.3% | 7.5% |
| A': deployed, cut-offs shifted to B's approval rate | 0.0% | 0.0% | - | 29.5% | 6.5% |
| B: retrained + rules | 0.0% | 0.0% | - | 67.3% | 11.2% |
| C: retrained + thin-file cap (m = 1) | 0.0% | 0.0% | - | 67.3% | 11.2% |

# Correction to evaluation 3

`evaluate3.py` scored first loans (zero history) with the raw network and found the retrained model gives them a top score. The live system never does that: a wallet is unscored until its first repayment event, so its first decision is always the starter quota, and the contract then raises one tier per period. The n = 0 columns above show this. The thin-file risk that remains is for wallets with one or two completed loans.

# What the evidence says

- **The thin-file cap does not earn its place.** Each extra required loan removes risky approvals, but it removes reliable borrowers just as fast. In the validation sweeps, shifting the retrained model's plain cut-offs to the same approval rate beats the cap on risky approvals or false rejections (operating point 2, m = 3: cap 11.1% risky approved and 62.0% false rejection, plain shift 10.9% and 55.7%; operating point 1: cap 64.4% risky approved, plain shift 34.1%). The protocol therefore picks m = 1, which is the existing contract rule, so configuration C is the same as B. The contract's first-decision-is-the-starter-quota rule already does the work a zero-loan cap would.
- **The retrained model's gain survives, and does not come from the cap.** At operating point 2 (approved = tier 2 or above), B approves 13.0% of truly risky loans against 28.9% for A (24.6% for A with cut-offs shifted to a nearer approval rate), and loses 5.06% per unit of exposure against 6.00% (5.88% shifted). On deteriorating borrowers, risky loans approved fall from 42.2% to 15.6%; on strategic defaulters, from 32.5% to 15.5%.
- **The price is more good borrowers turned away and a weaker thin-file record.** False rejection is 37.9% against 33.2% for A at a nearer approval rate, and reliable loans get an average limit of 55.9 against 58.3. The retrained model also approves more wallets with only two completed loans (67.3% against 41.3%), and those approved are late more often (11.2% against 7.5%). On recovering borrowers, late among approved is 29.8% against 17.9%. So the thin-file weakness is real, but it sits at one or two completed loans and is better handled by where the cut-offs sit than by a cap.
- **The retrained model only works with new tier cut-offs.** It outputs P(on time), so its tier cut-offs (here 739 / 831 / 899) differ from the deployed 307 / 563 / 819, and they were set on validation data. At the deployed cut-offs the data is saturated (about 88% approved at tier 1 or above, rows labelled operating point 1), so that comparison says little.
- **Limits of all of this.** The simulator, the borrower types and the labels are ours, the retrained model is trained on exactly those behaviours, and the loss model assumes a fully drawn tier limit. A gain here is a gain at recovering behaviours we invented. It is not evidence about real borrowers.
