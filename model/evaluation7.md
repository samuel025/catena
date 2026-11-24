# Evaluation 7: matched approval rates

Evaluation only (`model/evaluate7.py`, seeded). Synthetic data. Each model is approved at the same share of loans (tier 2 or above under the contract rules); cut-offs were set on validation, test evaluated once. Mean of 3 seeds for the two retrained models.

| target approval | model | actual test approval | overall risky approved | false rejection | precision | recall | loss per loan | recovering low-risk approved | deteriorating risky approved | strategic risky approved |
|---|---|---|---|---|---|---|---|---|---|---|
| 30% | deployed | 34.9% | 19.0% | 40.9% | 87.0% | 38.4% | 1.83 | 17.0% | 28.2% | 22.2% |
| 30% | retrained six features | 30.8% | 11.0% | 41.3% | 89.3% | 34.8% | 1.20 | 2.9% | 12.7% | 13.8% |
| 30% | candidate: + recent ratio + trend | 31.5% | 11.4% | 41.7% | 89.5% | 35.7% | 1.37 | 14.9% | 13.7% | 13.1% |
| 40% | deployed | 45.8% | 27.6% | 29.5% | 85.6% | 49.6% | 2.46 | 25.3% | 40.5% | 31.2% |
| 40% | retrained six features | 41.3% | 14.2% | 34.9% | 87.8% | 45.8% | 2.63 | 4.9% | 17.9% | 16.2% |
| 40% | candidate: + recent ratio + trend | 42.2% | 15.1% | 32.6% | 87.8% | 46.9% | 1.99 | 24.7% | 18.4% | 16.0% |
| 50% | deployed | 57.5% | 39.3% | 22.5% | 83.6% | 60.8% | 3.38 | 37.2% | 56.3% | 44.0% |
| 50% | retrained six features | 54.6% | 24.2% | 25.0% | 86.2% | 59.6% | 3.12 | 23.5% | 36.0% | 22.8% |
| 50% | candidate: + recent ratio + trend | 52.9% | 22.2% | 28.9% | 86.1% | 57.5% | 2.88 | 53.3% | 29.2% | 18.6% |

## Reading this

- Matching on validation does not transfer exactly: test approval rates still differ by up to 3 points, and the deployed model approves slightly more at every target. Read the 'actual test approval' column.
- At the 40% target the candidate approves 15.1% of truly risky loans against 27.6% for the deployed model, and 18.4% against 40.5% of deteriorating borrowers, while approving about as many low-risk recovering loans (24.7% against 25.3%). The six-feature retrained model has the same risk gains but approves only 4.9% of recovering loans.
- Its false rejection is 32.6% against 29.5% for the deployed model, at 3.6 points lower approval, so part of that gap is volume.
- Loss per loan is noisy across targets (a few strategic-defaulter loans at a 100-unit limit dominate it); do not read small differences.
- All of this is the simulator's own behaviour. It does not show how the candidate would do on real borrowers, and the deployed model remains the six-input one.

