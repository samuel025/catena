# Extra evaluations

Synthetic data only. Reproduce with `model/evaluate.py`.

## A. Risky borrowers, same held-out set as the model card (6000 profiles)

No defaults are simulated (a default is a hard rule), so 'risky' means true quality below the tier-1 bar. The last column is the share of those borrowers a scorer would approve for credit.

| scorer | MSE | tier acc | over-lend | severe over-lend | true tier 0: wrongly approved |
|---|---|---|---|---|---|
| MLP (shipped, integer) | 0.0188 | 66.6% | 14.3% | 0.4% | 24.5% of 2470 |
| fitted linear | 0.0198 | 65.9% | 15.5% | 0.2% | 29.1% of 2470 |
| transparent scorecard | 0.0304 | 58.4% | 19.2% | 1.1% | 20.0% of 2470 |
| hand-set formula | 0.0411 | 46.7% | 42.5% | 5.1% | 46.8% of 2470 |

## B. Unseen borrower populations

The generator mixes three populations of borrowers. For each row the models are trained on the other two and tested on the one left out (shipped hyper-parameters, 12000 training profiles, 200 epochs, so the numbers differ a little from section A).

### Held out: reliable Beta(8,2)

| scorer | MSE | tier acc | over-lend | severe over-lend | true tier 0: wrongly approved |
|---|---|---|---|---|---|
| MLP (integer) | 0.0402 | 43.0% | 1.7% | 0.0% | 39.6% of 48 |
| fitted linear | 0.0457 | 37.5% | 1.2% | 0.0% | 41.7% of 48 |
| transparent scorecard | 0.0477 | 38.8% | 24.5% | 0.9% | 41.7% of 48 |

### Held out: unreliable Beta(2,6)

| scorer | MSE | tier acc | over-lend | severe over-lend | true tier 0: wrongly approved |
|---|---|---|---|---|---|
| MLP (integer) | 0.0395 | 66.0% | 32.3% | 1.5% | 35.2% of 3451 |
| fitted linear | 0.0372 | 64.7% | 33.7% | 1.7% | 36.7% of 3451 |
| transparent scorecard | 0.0169 | 79.6% | 14.5% | 0.6% | 14.9% of 3451 |

### Held out: mixed Beta(3,3)

| scorer | MSE | tier acc | over-lend | severe over-lend | true tier 0: wrongly approved |
|---|---|---|---|---|---|
| MLP (integer) | 0.0192 | 63.9% | 19.7% | 0.7% | 28.2% of 1509 |
| fitted linear | 0.0195 | 63.5% | 21.8% | 0.7% | 35.1% of 1509 |
| transparent scorecard | 0.0288 | 56.6% | 18.8% | 1.6% | 23.5% of 1509 |

## Reading this

- Monotonicity (more on-time repayments never lowers a score, more late ones never raise it) is a safety property. It does not make the scores accurate.
- The true quality in the generator is close to linear in the features, so a fitted linear formula is a strong opponent and the MLP's edge, if any, is small. We do not claim a large accuracy win.
- 'Wrongly approved' is the number a lender should care about most. Compare it across rows before trusting any single accuracy figure.
