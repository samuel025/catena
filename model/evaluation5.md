# Evaluation 5: checks before any redeploy

Read-only (`model/evaluate5.py`, seeded). Synthetic data.

## 1. Is the retrained output a probability? Reliability on test loans (scored loans only)

| predicted P(on time) bin | loans | mean predicted | observed on-time |
|---|---|---|---|
| 0.50-0.70 | 3292 | 0.677 | 0.600 |
| 0.70-0.80 | 10879 | 0.733 | 0.738 |
| 0.80-0.85 | 3004 | 0.829 | 0.832 |
| 0.85-0.90 | 5490 | 0.876 | 0.886 |
| 0.90-0.95 | 3494 | 0.917 | 0.917 |
| 0.95-1.00 | 87 | 0.955 | 0.977 |

Expected calibration error 0.014. Brier score 0.157 (always predicting the base rate 0.787: 0.168). The deployed model's output is a quality index tuned to thresholds, not a probability; compare it with this table only as a ranking.

## 2. Recovering borrowers: are they punished after they improve?

Test loans of recovering borrowers, grouped by their real risk at that loan. Share given tier 2 or above and the late rate among those approved (matched-quartile operating point, existing rules).

| real risk now | loans | deployed: approved | late among approved | retrained: approved | late among approved |
|---|---|---|---|---|---|
| 0-15% | 696 | 42% | 8% | 4% | 4% |
| 15-30% | 1185 | 18% | 25% | 3% | 23% |
| 30-45% | 996 | 7% | 33% | 7% | 38% |
| 45-100% | 558 | 2% | 54% | 6% | 41% |

Reading: if the retrained model punished improvement, its approved share in the low-risk rows would be clearly below the deployed model's. Compare the rows above before concluding anything.
