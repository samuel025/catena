# Demo video script (target 2:50, hard limit 3:00)

Judges score Execution (on-chain reactive transactions and callbacks), Integration, Usefulness, Craft. This script
shows a live run, three wallet stories, the safety test, and the honest numbers.

## Before filming (do once, off camera)
1. **Shorten the timers.** The default 60 s raise period and loan period do not fit in 3 minutes. Redeploy for filming:
   `REACTIVE_FUND=0.2ether POOL_FUND=0.002ether RAISE_PERIOD=15 LOAN_PERIOD=40 GRACE=15 script/deploy.sh && script/gen_web_config.sh`
2. **Fund it.** `script/check_funds.sh`. Budget about 1 lREACT for rehearsals plus the take (about 0.03 lREACT per reactive tx).
   Every demo script refuses to start if funds are low. Top up with `depositTo` (the guard prints the command).
3. **Pre-stage the defaulter.** Run `script/demo_wallets.sh` up to the unpaid loan, or borrow with a fresh wallet about 60 s
   before you reach that scene, so `markDefault` is ready when you need it.
4. **Serve the page.** `cd web && python3 -m http.server 8000`, open it in a second window next to the terminal.
5. **Fresh wallet for the hero story.** `script/new_actor.sh`, then `export ACTOR_KEY=...` and open `web/index.html?w=<address>`.
6. Rehearse once. Cut waits in the edit rather than waiting live.

## Timeline

| Time | Screen | Say | Proves |
|------|--------|-----|--------|
| 0:00 to 0:15 | Architecture picture from the doc (2 pools, 1 reactive contract, 4 arrows) | "Crypto lending asks for more collateral than the loan, and your repayment record on one chain is invisible on another. Catena is a cross-chain credit passport. A small neural network runs inside a reactive contract and sets your borrow limit on both chains." | Idea, AI in the running system |
| 0:15 to 0:40 | Page for the fresh wallet (tier 0, quota 2 and 2). Terminal: `script/demo_capital.sh` first half, or `cast send $POOL_UNI_COLL 'borrow(uint256)' 20e18` | "This wallet has no history. A collateral-only pool rejects a 20 unit borrow. Same on our pool: its limit is the small starter quota." | The before |
| 0:40 to 1:15 | Terminal: `ACTOR_KEY=... script/demo.sh`. Page updates live. | "It borrows and repays on time on Base. Watch Unichain, a different chain that has never seen this wallet." Point at quota rising on both chains, the score, the "Why" card, the tx hashes. | Event to reactive tx to callbacks on 2 chains; model sets limits |
| 1:15 to 1:30 | Terminal: borrow 20 on the Catena pool on Unichain: approved. | "Same borrow that was rejected. Approved, with no collateral, because of its Base history." | Usefulness: capital efficiency |
| 1:30 to 1:55 | Defaulter wallet page, then `markDefault`. | "A default is a hard rule outside the model. Both quotas drop to zero at once, and the recorded reason says default, not a model guess." | Safety rules, cut applies immediately |
| 1:55 to 2:20 | Terminal: `ACTOR_KEY=... script/security_test.sh` | "Two chains cannot enforce one shared limit through async callbacks. Fixed per-chain quotas bound the worst case. We draw the full quota on both chains at once, and total exposure equals the total limit." | Double-draw handled and tested |
| 2:20 to 2:50 | README "Measured" table, model card results table | "react() costs about 190k gas of a 900k cap, one forward pass about 37k. Python and Solidity match bit for bit across 842 events. Honest result: our network scores 66.7 percent tier accuracy against 65.9 for a plain fitted formula. The data is synthetic, so we claim a working on-chain model, not a big accuracy win." | Craft, honesty, gas, parity |
| 2:50 to 3:00 | Repo link, contract addresses on Reactscan | "Open source, all addresses and transaction hashes are in the submission." | Submission items |

## Do not claim
- "Sub-second": the measured loop is about 1 to 3 seconds (see README), with 1 s timestamp resolution.
- That the AI beats a plain formula by a lot, or predicts real defaults. The data is synthetic.
- That identity is solved. It is address-based; a defaulter can start a new wallet at tier 0.

## If something goes wrong on camera
A silent hang almost always means the reactive contract is out of lREACT. Run `script/check_funds.sh` and top up.
