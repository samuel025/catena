# Evaluation 3: where do the scorers fail, and why?

Evidence only. No features, weights, training or contracts were changed. Reproduce with `model/evaluate3.py` (seeded; same simulated loans as `evaluate2.py`). Synthetic data throughout.

## 1. Per borrower type, test months 17-23, each scorer approves the top 50% of ALL test loans

Per cell: share of the type's truly risky loans (real risk > 30% at that moment) that were approved / share of approved loans of that type that went late or defaulted. The approval threshold is global, so a scorer cannot look good on one type by being stricter overall.

| type | test loans | truly risky | deployed MLP | retrained MLP | fitted linear | scorecard |
|---|---|---|---|---|---|---|
| consistent | 7941 | 0 | no risky loans / 4% | no risky loans / 4% | no risky loans / 4% | no risky loans / 5% |
| new / thin file | 914 | 0 | no risky loans / 7% | no risky loans / 12% | no risky loans / 11% | no risky loans / 11% |
| occasional late | 4653 | 0 | no risky loans / 13% | no risky loans / 14% | no risky loans / 14% | no risky loans / 14% |
| deteriorating | 3904 | 2268 | 43% / 33% | 17% / 24% | 17% / 23% | 44% / 31% |
| over-leveraged | 3615 | 0 | no risky loans / 13% | no risky loans / 15% | no risky loans / 15% | no risky loans / 14% |
| recovering | 3435 | 1554 | 8% / 20% | 21% / 43% | 21% / 39% | 14% / 22% |
| strategic defaulter | 3198 | 1854 | 33% / 36% | 16% / 20% | 16% / 20% | 34% / 34% |

## 2. Do the six features see it coming? Event study around the first loan where real risk exceeds 30%

### deteriorating (921 borrowers who turn risky after at least one safe loan)

Rows are loans relative to the turn (0 = first loan with real risk above 30%).

| loans from turn | n | mean real risk | mean retrained score | mean on-time | mean late ratio | mean recency | approved (retrained) | approved (linear) | approved (scorecard) |
|---|---|---|---|---|---|---|---|---|---|
| -4 | 704 | 12% | 861 | 182 | 53 | 163 | 87% | 84% | 62% |
| -3 | 853 | 15% | 855 | 226 | 61 | 190 | 81% | 78% | 66% |
| -2 | 920 | 20% | 845 | 292 | 80 | 231 | 73% | 71% | 70% |
| -1 | 921 | 27% | 828 | 373 | 118 | 263 | 60% | 61% | 68% |
| +0 | 921 | 33% | 805 | 448 | 152 | 258 | 44% | 44% | 63% |
| +1 | 855 | 40% | 783 | 509 | 190 | 235 | 29% | 29% | 53% |
| +2 | 764 | 46% | 765 | 578 | 221 | 207 | 17% | 17% | 46% |
| +3 | 593 | 49% | 753 | 659 | 245 | 169 | 10% | 9% | 38% |
| +4 | 407 | 52% | 742 | 735 | 271 | 130 | 5% | 4% | 32% |

Loans after the turn until the scorer first stops approving that borrower (median; borrowers it never stopped approving before they ran out of loans in the window):

| scorer | median lag (loans) | never stopped |
|---|---|---|
| deployed MLP | 0.0 | 251 of 921 |
| retrained MLP | 0.0 | 105 of 921 |
| fitted linear | 0.0 | 105 of 921 |
| scorecard | 0.0 | 252 of 921 |

### strategic defaulter (752 borrowers who turn risky after at least one safe loan)

Rows are loans relative to the turn (0 = first loan with real risk above 30%).

| loans from turn | n | mean real risk | mean retrained score | mean on-time | mean late ratio | mean recency | approved (retrained) | approved (linear) | approved (scorecard) |
|---|---|---|---|---|---|---|---|---|---|
| -4 | 560 | 5% | 865 | 193 | 52 | 177 | 87% | 84% | 64% |
| -3 | 687 | 6% | 865 | 235 | 53 | 216 | 86% | 84% | 68% |
| -2 | 752 | 6% | 867 | 304 | 53 | 278 | 84% | 84% | 76% |
| -1 | 752 | 6% | 867 | 401 | 62 | 363 | 80% | 81% | 84% |
| +0 | 752 | 85% | 867 | 497 | 59 | 438 | 76% | 77% | 85% |
| +1 | 697 | 85% | 761 | 510 | 208 | 89 | 13% | 13% | 55% |
| +2 | 604 | 85% | 734 | 527 | 305 | 33 | 2% | 2% | 22% |
| +3 | 466 | 85% | 721 | 574 | 365 | 16 | 1% | 0% | 8% |
| +4 | 332 | 85% | 713 | 618 | 404 | 19 | 0% | 0% | 7% |

Loans after the turn until the scorer first stops approving that borrower (median; borrowers it never stopped approving before they ran out of loans in the window):

| scorer | median lag (loans) | never stopped |
|---|---|---|
| deployed MLP | 1.0 | 129 of 752 |
| retrained MLP | 1.0 | 59 of 752 |
| fitted linear | 1.0 | 59 of 752 |
| scorecard | 1.0 | 134 of 752 |

Reference: consistent borrowers (never risky), averaged by loan number.

| loan number | mean retrained score | mean on-time | mean late ratio | mean recency | approved (retrained) |
|---|---|---|---|---|---|
| 0 | 859 | 0 | 0 | 0 | 95% |
| 2 | 869 | 194 | 49 | 189 | 91% |
| 4 | 868 | 389 | 51 | 361 | 82% |
| 6 | 869 | 584 | 51 | 521 | 76% |
| 8 | 869 | 778 | 51 | 663 | 69% |
| 10 | 872 | 975 | 49 | 796 | 65% |

## 3. Can the six features separate the loans that are risky? AUC of each scorer (test months)

AUC of the score for 'this loan will be on time' on the loans where real risk is high (>30%) versus low (<10%), per type. 0.5 = no information.

| type | deployed MLP | retrained MLP | fitted linear | scorecard |
|---|---|---|---|---|
| consistent | (too few high- or low-risk loans: 0 / 6871) | | | |
| new / thin file | (too few high- or low-risk loans: 0 / 383) | | | |
| occasional late | (too few high- or low-risk loans: 0 / 847) | | | |
| deteriorating | 0.44 | 0.89 | 0.90 | 0.49 |
| over-leveraged | (too few high- or low-risk loans: 0 / 278) | | | |
| recovering | 0.88 | 0.69 | 0.44 | 0.86 |
| strategic defaulter | 0.72 | 0.89 | 0.91 | 0.75 |

## 4. Wallets with no history at all (their first loan, all types, whole simulated set)

Thresholds are the same as above (each scorer approves the top 50% of test loans). A scorer that gives an unknown wallet a high score contradicts the thin-file policy (starter quota for unscored wallets).

| scorer | mean score at first loan | approved | late/default among approved |
|---|---|---|---|
| deployed MLP | 401 | 0% | nan% |
| retrained MLP | 853 | 90% | 14% |
| fitted linear | 873 | 75% | 13% |
| scorecard | 373 | 0% | nan% |
| (all first loans, no filter) | | 100% | 14% |

## 5. Leakage and novelty checks

- **Look-ahead in features:** recomputed on-time count, late ratio, last-five consistency and streak for 11802 loans from only the borrower's earlier outcomes. Mismatches: 0. Debt ratio and history age are not functions of any outcome.
- **Time order:** every test loan is in months 17-23, every training loan in months 0-13. Latest training month 13, earliest test month 17.
- **Same borrowers in train and test:** 56% of test loans belong to a borrower who also has training loans (earlier ones). This is how a temporal split of a live system works (the same wallets keep borrowing), but it means the model has seen those borrowers' early behaviour, which is not a population-level holdout.
- **Is section B's test type novel?** Share of borrowers (4+ loans) whose real risk rises by more than 30 points over their history: 0% of the training borrowers when deteriorating and strategic types are excluded (5915 borrowers), 82% of the held-out types (1968 borrowers). Training without them removes almost all the transitions, so section B genuinely tests an unseen behaviour pattern. Recovering borrowers (risk falling) remain in training and are the mirror image, not the same pattern.
- **Section A:** with all seven types in training, the same share is 20% of all borrowers, so those transitions are represented there.


## What the evidence says

- **Strategic defaulters cannot be caught by any history-based scorer on their first bad loan.** Until the turn, their late ratio, streak and on-time count look exactly like a reliable borrower's (late ratio about 50-60 on a 1024 scale, flat). One loan after the turn the retrained score drops and approval falls from 76% to 13%. The exposure is one loan. That is an information limit, not a model flaw, and it is what the per-chain quota caps and the default rule are for.
- **Deteriorating borrowers do leave a trace, and the retrained model uses it; the deployed one does not.** The late ratio climbs from about 53 to 152 before the turn. Retrained approvals fall 87% to 44% over the four loans before it (AUC 0.89 on high- versus low-risk loans). The deployed network scores them AUC 0.44, below chance: it rewards the growing on-time count and history length more than it penalises the rising late ratio, so it approves 43% of the risky ones. That is a real weakness of the deployed weights, found only on this harder data.
- **The retrained model is not a drop-in replacement.** It gives a wallet with no history a mean score of 853 (tier 3) and approves 90% of first loans, because the typical borrower in this data is reliable. The deployed model scores them 401 and approves none. That contradicts the thin-file policy (starter quota, one tier per period). Retraining would need a policy cap on thin files first. It also explains why the retrained model does worse than the deployed one on recovering borrowers (43% late among approved versus 20%): their risky loans are early, when history is thin.
- **No look-ahead leakage in the features** (0 mismatches). The temporal split holds. Test loans share borrowers with training loans (56%), which is realistic for a live system but is not a population holdout. Section B's held-out types really are novel: 0% of training borrowers show a risk rise of more than 30 points, against 82% of the held-out types.
- **Decision input, not a decision.** The deployed model's blind spot to deterioration is real but bounded in practice by the hard rules: late repayments are visible on-chain and a tier cut is immediate, the quota caps exposure per chain, and one default zeroes the unsecured limit. We have not changed weights, features, training or the deployment.
