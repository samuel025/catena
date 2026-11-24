# Catena

A cross-chain credit passport for the Reactive Omni Buildathon (Reactive Meets AI track).
A reactive contract on Reactive Lasna watches loan events on Base Sepolia and Unichain Sepolia, scores each
borrower with a small neural network that runs **inside** `react()`, and sets per-chain borrow quotas by callback.
Test networks, fake money. Not production credit scoring.

## How it works
1. Pools on each chain emit `Borrowed`, `Repaid(late?)` and `Defaulted` events.
2. `CatenaReactive` keeps one passport per wallet (six features), dedups events, and runs the MLP in fixed-point integer math.
3. The score gives a tier, and the tier sets a total limit that is split into fixed per-chain quotas, pushed by callback.
4. Hard rules sit outside the model: a default forces zero, cuts apply at once, raises climb one tier per period,
   new wallets start at tier 0 with a small starter quota, and stale or replayed updates are ignored.
5. When a tier changes the contract records the biggest helping and hurting inputs (model sensitivity, not the definitive cause).

What the security design guarantees, and what it does not:

| Guarantee | Holds? |
|---|---|
| Concurrent draws on several chains cannot exceed the sum of the quotas currently installed (`script/security_test.sh`) | Yes, whatever the callback latency |
| An older callback cannot overwrite a newer assessment (score version check in the pool) | Yes (`test_poolIgnoresStaleVersion`) |
| A default flagged on a pool removes that pool's unsecured limit immediately | Yes (`defaultFlagged`, no callback needed) |
| A default on one chain blocks borrowing on the other chain immediately | **No.** The other pool keeps its old quota until the zero-quota callback arrives, a window of about 1 to 3 seconds measured on testnet. Exposure in that window is bounded by the old quota minus debt (`test_defaultBlocksLocallyAtOnceAndRemotelyAfterCallback`) |

Quotas bound concurrent borrowing against the allocations installed at that moment. They do not make cross-chain
revocation instantaneous. Removing the window would need a short-lived authorization the pool checks before each draw,
which this prototype leaves out.

## Hybrid lending (not all-or-nothing)
A pool's borrow limit is `unsecured quota from history + half of the posted collateral` (`borrowLimit`). Good history
raises the unsecured part, so less collateral is needed. A default removes the unsecured part at once on the pool that
sees it, and on the other chain when the callback lands, but a borrower's own collateral still supports their own
secured loans. The collateral-only pool is the same contract with the unsecured part switched off.
This demonstrates permissioning from a cross-chain repayment record. It does not show that unsecured lending is
economically safe: collateral here is accounting only (no withdrawal, no liquidation), and a real lender would keep its
own risk and liquidity controls.

## Layout
| Path | What |
|---|---|
| `src/CatenaPool.sol` | demo pool + callback receiver, same code on every chain; `collateralOnly` mode is the demo's "before" case |
| `src/CatenaReactive.sol` | passport state, features, rules, reasons, callbacks |
| `src/Mlp.sol` | GENERATED integer MLP (6 -> 8 ReLU -> 1), monotone by construction |
| `model/train.py` | synthetic data, constrained training, quantization, export, evaluation |
| `model/replay.py` | Python spec of the contract's state machine, used for whole-history parity tests |
| `model/model_card.md` | data rules, metrics, baselines, limits (read this before trusting any number) |
| `model/evaluation.md` | extra checks: risky-borrower approvals, leave-one-population-out, transparent scorecard baseline (`model/evaluate.py`) |
| `test/` | contract tests, Python-vs-Solidity parity (vectors and 842-event histories), monotone fuzz, overflow |
| `script/` | `deploy.sh`, `demo.sh`, `demo_wallets.sh`, `demo_capital.sh`, `security_test.sh`, `latency.sh`, `check_funds.sh`, `new_actor.sh`, `gen_web_config.sh` |
| `web/` | static page: look up any wallet and see tier, score, quotas on both chains, reasons and scorings, read live from the RPCs (no backend). `cd web && python3 -m http.server`, open `?w=<address>` |
| `docs/DEMO_SCRIPT.md` | shot-by-shot script for the under-3-minute video, with the pre-filming checklist |

## Run
```
forge install foundry-rs/forge-std   # test library (reactive-lib-omni is a submodule: git submodule update --init)
forge test                        # 28 tests
python3 -m venv .venv && .venv/bin/pip install numpy
.venv/bin/python model/train.py && .venv/bin/python model/replay.py   # regenerate model + test vectors
cp .env.example .env              # PRIVATE_KEY (throwaway testnet key), RPCs
script/deploy.sh                  # reactive first, then pools (callback sender is immutable)
script/check_funds.sh             # reactive contract needs lREACT, each pool needs native gas
script/demo.sh && script/demo_capital.sh && script/demo_wallets.sh && script/security_test.sh
```
Funding matters: each reactive transaction costs about 0.03 lREACT at 100 gwei and every pool event triggers one.
A contract in debt silently stops receiving events. lREACT comes from the faucet contracts in the Reactive docs.

## Deployed (testnets, filming timers: raise period 15 s, loan 40 s, grace 15 s)
| Contract | Chain | Address |
|---|---|---|
| CatenaReactive | Reactive Lasna (5318007) | `0x36479f19b034ee34A316fCe239eC219FA1Bfe219` |
| CatenaPool | Base Sepolia (84532) | `0x623646b15a4f5220D50c97B20EAD88e32c43Bb44` |
| CatenaPool | Unichain Sepolia (1301) | `0xc66ca4091E0f07E01a10E2200ffFa7F16FeDBB31` |
| CatenaPool (collateral-only, demo "before") | Unichain Sepolia | `0x8261f88E31faD3d6f0695AE2188995152e98D38a` |

Earlier deployments are archived in `deployments.v*.env`. The timers are constructor parameters (`script/deploy.sh`
defaults are 60 s / 60 s / 30 s).

## Measured (Lasna, Base Sepolia, Unichain Sepolia)
- `react()` for a repay including two callbacks: 185k to 202k gas (cap 900k). One MLP forward pass: about 37k gas.
- Origin event to destination callback (`script/latency.sh`, 4 rounds, block timestamps with 1 s resolution):
  event on Base to quota update on Base 0 to 2 s (mean 1.0 s); to the quota update on Unichain 1 to 3 s (mean 2.0 s, cross-chain clocks can differ by about 1 s).
- Model, held-out synthetic data: MLP 66.7% tier accuracy vs 65.9% for a fitted linear formula, so the
  win over a plain formula is small. See `model/model_card.md`.

## Chain facts (Reactive docs)
Lasna chain ID 5318007, system contract `0x8888…8888`. Callback proxies: Base Sepolia `0x476F…0585`,
Unichain Sepolia `0x775c…66C1`.

## Limits
Synthetic training data; address-based identity (a defaulter can open a new wallet, which starts at tier 0);
one scripted demo, not a product.

**Source verification is not done.** The Reactive docs point to Sourcify, but Sourcify's compile worker fails with
"Failed fetching solc" for 0.8.29 and 0.8.30 (the Omni library requires `^0.8.29`), and Reactscan has no verification
API. Reproduce locally: `forge build --build-info`, then POST the standard JSON input to
`https://sourcify.dev/server/v2/verify/5318007/<address>`. The source is public in this repo and the build is deterministic
(solc 0.8.30, optimizer 200 runs, cancun).

## Disclosure
Developed with AI assistance (Claude Code).
