# Evaluation 6: does recent repayment behaviour add information?

Python only (`model/evaluate6.py`, seeded). Synthetic data; nothing deployed or changed. Method and selection rule are in the script's header.

## Validation (months 14-16): all candidates, mean of 3 training seeds

Approved = tier 2 or above. 'Recovering low-risk approved' = share of recovering borrowers' loans with real risk under 30% that get tier 2 or above. Risky approved = loans with real risk over 30%.

| candidate | overall risky approved | false rejection | loss per loan | recovering low-risk approved | deteriorating risky approved | strategic risky approved | consistent late among approved |
|---|---|---|---|---|---|---|---|
| deployed model | 26.4% | 39.5% | 2.25 | 23.5% | 43.4% | 36.2% | 3.9% |
| A  six features | 15.5% | 43.7% | 1.63 | 4.0% | 22.2% | 19.9% | 4.2% |
| B  + recent late ratio (w=3) | 16.5% | 39.6% | 1.71 | 20.0% | 23.9% | 20.5% | 3.8% |
| B  + recent late ratio (w=5) | 15.5% | 41.3% | 1.62 | 9.0% | 22.1% | 20.1% | 4.1% |
| B  + recent late ratio (w=10) | 15.5% | 43.7% | 1.62 | 3.9% | 22.2% | 19.8% | 4.2% |
| C  + recent ratio + trend (w=3) | 16.8% | 41.0% | 1.59 | 21.4% | 23.1% | 19.9% | 3.7% |
| C  + recent ratio + trend (w=5) | 15.9% | 41.0% | 1.61 | 21.8% | 21.9% | 20.7% | 3.9% |
| C  + recent ratio + trend (w=10) | 15.5% | 43.3% | 1.66 | 5.3% | 22.1% | 20.0% | 4.2% |

Selection rule (validation only): deteriorating risky approvals must stay within 2 points of A (22.2%); then most low-risk recovering loans approved. Chosen: **C  + recent ratio + trend (w=5)**.

## Test (months 17-23), evaluated once, mean of 3 seeds (range of the selected model in the next table)

| model | overall risky approved | false rejection | precision | recall | loss per loan | recovering low-risk approved | deteriorating risky approved | strategic risky approved |
|---|---|---|---|---|---|---|---|---|
| deployed model | 28.9% | 28.2% | 85.3% | 51.1% | 2.57 | 26.7% | 42.2% | 32.5% |
| A  six features (retrained) | 13.1% | 37.7% | 88.2% | 41.4% | 1.80 | 3.5% | 15.7% | 15.6% |
| C  + recent ratio + trend (w=5) (selected) | 14.0% | 34.0% | 88.3% | 43.3% | 1.69 | 20.1% | 17.0% | 15.5% |

## Test by borrower type: risky approved / late among approved / loss per loan

| type | deployed model | A  six features (retrained) | C  + recent ratio + trend (w=5) (selected) |
|---|---|---|---|
| consistent | no risky loans / 4.1% / 0.65 | no risky loans / 3.9% / 0.52 | no risky loans / 3.7% / 0.46 |
| new / thin file | no risky loans / 8.2% / 0.67 | no risky loans / 12.4% / 0.77 | no risky loans / 11.9% / 0.78 |
| occasional late | no risky loans / 12.7% / 1.53 | no risky loans / 13.5% / 1.18 | no risky loans / 12.6% / 1.22 |
| deteriorating | 42.2% / 34.0% / 3.48 | 15.7% / 28.7% / 2.41 | 17.0% / 28.5% / 2.09 |
| over-leveraged | no risky loans / 13.3% / 0.92 | no risky loans / 13.7% / 0.81 | no risky loans / 12.9% / 0.75 |
| recovering | 5.3% / 17.9% / 0.91 | 6.4% / 29.3% / 0.68 | 7.8% / 21.7% / 1.07 |
| strategic defaulter | 32.5% / 38.8% / 11.94 | 15.6% / 24.6% / 7.72 | 15.5% / 25.1% / 6.97 |

## Seed spread on the test set (selected vs six-feature)

| metric | selected | six features |
|---|---|---|
| recovering low-risk approved | 19.3% to 21.4% | 3.3% to 3.6% |
| deteriorating risky approved | 16.7% to 17.2% | 15.6% to 15.9% |
| strategic risky approved | 15.4% to 15.6% | 15.5% to 15.6% |

## Calibration of the selected model (simulated data only)

| predicted bin | loans | mean predicted | observed on-time |
|---|---|---|---|
| 0.00-0.50 | 146 | 0.476 | 0.171 |
| 0.50-0.70 | 4185 | 0.635 | 0.565 |
| 0.70-0.80 | 7546 | 0.732 | 0.759 |
| 0.80-0.85 | 5431 | 0.826 | 0.829 |
| 0.85-0.90 | 6428 | 0.875 | 0.892 |
| 0.90-0.95 | 2508 | 0.914 | 0.918 |

Expected calibration error 0.026. This describes the simulator's own outcomes, not real borrowers.

## Monotone check (integer weights, seed 1, 2000 random trials)

- A  six features: 0 violations
- B  + recent late ratio (w=3): 0 violations
- B  + recent late ratio (w=5): 0 violations
- B  + recent late ratio (w=10): 0 violations
- C  + recent ratio + trend (w=3): 0 violations
- C  + recent ratio + trend (w=5): 0 violations
- C  + recent ratio + trend (w=10): 0 violations
