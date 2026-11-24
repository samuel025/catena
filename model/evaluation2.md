# Harder evaluation: trajectories, defaults, temporal split

Reproduce with `model/evaluate2.py` (seeded). Synthetic data; read the caveats at the end.

Data: 71931 loans from 9000 borrowers of seven types. Share of loans late or defaulted: 19.0%, defaulted: 7.0%.

Columns: among the loans each scorer approves at the stated approval rate, how many were then late/defaulted, how many were truly risky (the borrower's real risk at that moment above 30%), and how many truly reliable borrowers (risk below 10%) it turned away.

## A. Temporal split: train months 0-13 (32142 loans), test months 17-23 (27660 loans)

| scorer | approve top | next loan late/default among approved | default among approved | risky borrowers approved | reliable borrowers rejected |
|---|---|---|---|---|---|
| shipped MLP (trained on the old generator) | 40% | 13.2% | 5.4% | 22.4% | 33.6% |
| shipped MLP (trained on the old generator) | 60% | 15.6% | 6.1% | 38.8% | 15.8% |
| MLP retrained on trajectory data | 40% | 10.8% | 4.1% | 14.2% | 26.2% |
| MLP retrained on trajectory data | 60% | 12.9% | 4.3% | 22.5% | 13.1% |
| MLP, cost-sensitive (bad outcome x3) | 40% | 10.8% | 4.1% | 14.5% | 25.8% |
| MLP, cost-sensitive (bad outcome x3) | 60% | 13.0% | 4.3% | 23.1% | 12.8% |
| MLP, cost-sensitive (bad outcome x6) | 40% | 10.7% | 4.1% | 14.2% | 26.1% |
| MLP, cost-sensitive (bad outcome x6) | 60% | 12.8% | 4.2% | 22.4% | 13.2% |
| retrained MLP + confidence shrink | 40% | 11.1% | 4.2% | 14.1% | 28.9% |
| retrained MLP + confidence shrink | 60% | 13.2% | 4.3% | 26.2% | 15.3% |
| fitted linear | 40% | 10.8% | 4.1% | 14.1% | 26.1% |
| fitted linear | 60% | 13.1% | 4.2% | 24.8% | 14.5% |
| transparent scorecard | 40% | 13.1% | 4.7% | 17.7% | 39.6% |
| transparent scorecard | 60% | 14.5% | 5.4% | 32.5% | 14.9% |
| hand-set formula | 40% | 15.9% | 6.1% | 26.4% | 45.9% |
| hand-set formula | 60% | 17.3% | 6.7% | 44.3% | 25.0% |

## B. Unseen borrower types: trained without deteriorating and strategic borrowers, tested on only those (7102 later loans)

| scorer | approve top | next loan late/default among approved | default among approved | risky borrowers approved | reliable borrowers rejected |
|---|---|---|---|---|---|
| shipped MLP (trained on the old generator) | 40% | 34.6% | 18.1% | 34.2% | 43.3% |
| shipped MLP (trained on the old generator) | 60% | 36.0% | 18.2% | 52.0% | 23.3% |
| MLP retrained on trajectory data | 40% | 30.4% | 15.5% | 28.4% | 29.8% |
| MLP retrained on trajectory data | 60% | 33.8% | 17.4% | 47.6% | 11.9% |
| MLP, cost-sensitive (bad outcome x3) | 40% | 30.1% | 15.3% | 27.7% | 29.0% |
| MLP, cost-sensitive (bad outcome x3) | 60% | 33.6% | 17.2% | 47.2% | 11.9% |
| MLP, cost-sensitive (bad outcome x6) | 40% | 30.6% | 15.5% | 28.6% | 30.4% |
| MLP, cost-sensitive (bad outcome x6) | 60% | 34.0% | 17.5% | 47.9% | 12.5% |
| retrained MLP + confidence shrink | 40% | 33.5% | 17.5% | 32.2% | 39.9% |
| retrained MLP + confidence shrink | 60% | 31.6% | 16.2% | 43.7% | 5.1% |
| fitted linear | 40% | 31.5% | 16.2% | 29.9% | 33.8% |
| fitted linear | 60% | 34.6% | 17.8% | 49.0% | 16.6% |
| transparent scorecard | 40% | 31.7% | 16.1% | 29.9% | 36.5% |
| transparent scorecard | 60% | 33.4% | 16.5% | 47.3% | 21.9% |
| hand-set formula | 40% | 42.7% | 21.7% | 44.2% | 64.9% |
| hand-set formula | 60% | 41.2% | 20.7% | 61.2% | 41.6% |

## C. Thin files only (fewer than 3 prior loans, 5678 test loans)

Does a scorer shut out borrowers who simply have no history? Reliable borrowers rejected, among truly reliable thin files:

| scorer | approve top 60% | reliable thin files rejected | risky thin files approved |
|---|---|---|---|
| shipped MLP (trained on the old generator) | 60% | 29.5% | 27.3% |
| MLP retrained on trajectory data | 60% | 13.1% | 34.5% |
| MLP, cost-sensitive (bad outcome x3) | 60% | 12.9% | 34.6% |
| MLP, cost-sensitive (bad outcome x6) | 60% | 12.6% | 34.5% |
| retrained MLP + confidence shrink | 60% | 19.1% | 34.8% |
| fitted linear | 60% | 14.7% | 32.6% |
| transparent scorecard | 60% | 31.5% | 26.8% |
| hand-set formula | 60% | 31.5% | 26.8% |

## What this shows

- **The shipped model is tuned to an easy generator.** On loans from changing borrowers, retraining the same 6-8-1 network on trajectory data cuts risky approvals at a 40% approval rate from 22.4% to 14.2% and next-loan late/default among approved loans from 13.2% to 10.8%. The architecture does not change; the training data does.
- **The network does not beat a fitted linear formula.** Retrained MLP and fitted linear are within noise of each other in every section (14.2% vs 14.1% risky approved at 40%). The earlier conclusion stands: the value is auditable on-chain inference, not an accuracy win.
- **Both beat the hand-made scorecard on risky approvals** at the same approval rate (14% vs 18% at 40%), but the gap is small and the scorecard is competitive on unseen borrower types (section B).
- **Cost-sensitive training did nothing useful.** Weights of 3 and 6 on bad loans leave every column within about a point of the unweighted model. A cost penalty changes where a score threshold sits, not much how borrowers rank, and this comparison fixes the approval rate.
- **The confidence shrink is mixed.** It helps reliable thin files a little at one approval rate and hurts risky-thin-file approvals at another. We do not adopt it.
- **Unseen types are hard for everyone.** Borrowers who deteriorate or turn strategic are approved far too often by every scorer (30-48% of risky ones approved). A snapshot of past repayments cannot see a defaulter who has not started defaulting yet. This is why the hard rules (default flag, one-tier raise per period, quota caps) matter more than the model.


## Reading this

- Compare scorers at the same approval rate. A scorer that approves fewer people looks safer by construction.
- 'Cost-sensitive' multiplies the training loss on loans that went bad. Look at both right-hand columns: if risky approvals fall only because more reliable borrowers are rejected, the cost penalty did not help.
- The synthetic risk model is ours, so every row measures how well a scorer recovers a behaviour we invented. It is a harder test than `train.py`'s generator, not evidence about real borrowers.
