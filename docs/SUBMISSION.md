# Catena: submission details (Reactive Meets AI)

Repository: https://github.com/samuel025/catena (MIT licensed). Everything here is on test networks with fake money.

## Deployed contracts

| Contract | Chain | Address |
|---|---|---|
| CatenaReactive (scores borrowers, runs the MLP) | Lasna | `0x36479f19b034ee34A316fCe239eC219FA1Bfe219` |
| CatenaPool | Base Sepolia | `0x623646b15a4f5220D50c97B20EAD88e32c43Bb44` |
| CatenaPool | Unichain Sepolia | `0xc66ca4091E0f07E01a10E2200ffFa7F16FeDBB31` |
| CatenaPool, collateral-only ("before" case) | Unichain Sepolia | `0x8261f88E31faD3d6f0695AE2188995152e98D38a` |

## One full loop, origin event to callbacks

Wallet `0x8D7A98ea6e6582fA4c210f915Ba84FFc69ffE508` borrowed 1 unit on Base Sepolia, then repaid it on time.

| Step | Chain | Transaction |
|---|---|---|
| 1. Borrowed event (origin) | Base Sepolia | [0xa38a15123ecdf99325b82b452a3e3935bef97fc7ba4e0a5cc00d938772be278f](https://sepolia.basescan.org/tx/0xa38a15123ecdf99325b82b452a3e3935bef97fc7ba4e0a5cc00d938772be278f) |
| 2. Repaid event (origin) | Base Sepolia | [0xaf3f313b4f576534c2268643ad89c911b786f82f229c32226fc81010266f47c7](https://sepolia.basescan.org/tx/0xaf3f313b4f576534c2268643ad89c911b786f82f229c32226fc81010266f47c7) |
| 3. Reactive transaction: update passport, run MLP, request callbacks | Lasna | [0x95156f24f03f8c5bcade1f572a531ee2f5d7a94bc2693885ba672f85d9a647cf](https://lasna.reactscan.net/tx/0x95156f24f03f8c5bcade1f572a531ee2f5d7a94bc2693885ba672f85d9a647cf) |
| 4. Callback: quota set | Base Sepolia | [0x82911e2fe5d345180ee04b9251b405977a531bf843efb921dad60639e587756d](https://sepolia.basescan.org/tx/0x82911e2fe5d345180ee04b9251b405977a531bf843efb921dad60639e587756d) |
| 5. Callback: quota set | Unichain Sepolia | [0x4780dac2b97ddec0d908f87a75e1ed6769c79225b5906c2a76237a6f30ebfff7](https://sepolia.uniscan.xyz/tx/0x4780dac2b97ddec0d908f87a75e1ed6769c79225b5906c2a76237a6f30ebfff7) |

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
