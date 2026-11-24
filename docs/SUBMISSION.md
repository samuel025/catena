# Catena: submission details (Reactive Meets AI)

Repository: https://github.com/samuel025/catena (MIT licensed). Everything here is on test networks with fake money.

## Deployed contracts

| Contract | Chain | Address |
|---|---|---|
| CatenaReactive (scores borrowers, runs the MLP) | Lasna | `0xc79198B4DBaB0d3C1D0454B737719b85cbC12475` |
| CatenaPool | Base Sepolia | `0x565d1B97E21d6D80bC5D4Eefe292EC199c0Ca469` |
| CatenaPool | Unichain Sepolia | `0xf715898abABFc48fD4D359cf68F5EBe56AC10D9D` |
| CatenaPool, collateral-only ("before" case) | Unichain Sepolia | `0x088F83Fd4Bc089Cb7D7845c1b32611aeB97eFd25` |

## One full loop, origin event to callbacks

Wallet `0x280CDC267f8D1AC55486848375b39f182ABbaC5f` borrowed 1 unit on Base Sepolia, then repaid it on time.

| Step | Chain | Transaction |
|---|---|---|
| 1. Borrowed event (origin) | Base Sepolia | [0xf4775476804efd8323d9ad194c214a9df57bb957eb9fa8ebf4e8b5fc48720487](https://sepolia.basescan.org/tx/0xf4775476804efd8323d9ad194c214a9df57bb957eb9fa8ebf4e8b5fc48720487) |
| 2. Repaid event (origin) | Base Sepolia | [0x536fc069d132f33480075fd2dd14c5f0c26b395aca2a9a517bc1eb05e8f1edca](https://sepolia.basescan.org/tx/0x536fc069d132f33480075fd2dd14c5f0c26b395aca2a9a517bc1eb05e8f1edca) |
| 3. Reactive transaction: update passport, run MLP, request callbacks | Lasna | [0x5bd416448caa1a1d5f47e855bcf9dd2e320457f496b5ddd33754ac7ca7cc52ab](https://lasna.reactscan.net/tx/0x5bd416448caa1a1d5f47e855bcf9dd2e320457f496b5ddd33754ac7ca7cc52ab) |
| 4. Callback: quota set | Base Sepolia | [0x7094aa39ccfd0530a2385eefa5faf251beb07a7dfbaa7c3c242dca7d52761177](https://sepolia.basescan.org/tx/0x7094aa39ccfd0530a2385eefa5faf251beb07a7dfbaa7c3c242dca7d52761177) |
| 5. Callback: quota set | Unichain Sepolia | [0x302346ea95227e8747137c8efbb82fd223be88220c0fa205707a39f7fd03d872](https://sepolia.uniscan.xyz/tx/0x302346ea95227e8747137c8efbb82fd223be88220c0fa205707a39f7fd03d872) |

Regenerate with `script/trace_loop.sh` (about 0.06 lREACT).

## What to look at
- The model runs inside the reactive transaction (step 3): one MLP forward pass is about 37k gas, and a repay with two callbacks costs 185k to 202k gas against a 900k cap.
- Latency from the Base repay to the quota update: same chain 0 to 2 s, Base to Unichain 1 to 3 s (see the README for the method and its 1 s resolution).
- `script/demo.sh`, `demo_capital.sh`, `demo_wallets.sh` and `security_test.sh` reproduce the scenarios: a repayment record raising limits on both chains, a collateral-only pool rejecting the borrow that the Catena pool approves, a default cutting both quotas to zero, and a double-draw bounded by the quotas.

## Honest limits
- Training data is synthetic. On it the MLP scores 66.7% tier accuracy against 65.9% for a fitted linear formula; a transparent scorecard approves fewer risky borrowers (see `model/evaluation.md`). We claim a working, monotone on-chain model, not a large accuracy win.
- A default on one chain reaches the other chain in about 1 to 3 s. The pool that sees it blocks unsecured borrowing at once; the other keeps its old quota until the callback lands.
- Contract source verification on Reactscan was attempted and is blocked (Sourcify cannot fetch solc 0.8.30, Reactscan has no verification API). The README explains how to reproduce the build, and we do not call the contracts verified.
- Addresses are the identity. A defaulter can open a new wallet, which starts at tier 0 with a small starter quota.
- Parts of this project were written with an AI coding assistant; the README discloses this.
