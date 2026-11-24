# Reproducing the deployments

This is **reproducibility evidence, not source verification**. Contract source verification on Reactscan and Sourcify was
attempted and is blocked (see the last section). Nothing here should be read as "verified".

## Toolchain
| Item | Value |
|---|---|
| Compiler | `solc 0.8.30` (`solc_version` in `foundry.toml`) |
| EVM version | `cancun` |
| Optimizer | enabled, 200 runs |
| Build tool | `forge 1.2.3-stable` |
| Dependencies | `reactive-lib-omni` at commit `3ade0dcf1d27e67e5783ef807e73a1b9e0c0cce8` (submodule), `forge-std` (test only) |

```
git clone --recurse-submodules https://github.com/samuel025/catena && cd catena
forge install foundry-rs/forge-std
forge build --build-info
```

## Constructor arguments
| Contract | Arguments |
|---|---|
| `CatenaReactive` | `raisePeriod = 15` |
| `CatenaPool` (Base Sepolia) | `callbackProxy = 0x476F44b11F5C942c58f4c8E3d0300E5710743585`, `reactive = <CatenaReactive>`, `collateralOnly = false`, `loanPeriod = 40`, `grace = 15` |
| `CatenaPool` (Unichain Sepolia) | `callbackProxy = 0x775c9B990ADe401060B78D0e98684eEf8d2466C1`, `reactive = <CatenaReactive>`, `collateralOnly = false`, `loanPeriod = 40`, `grace = 15` |
| `CatenaPool` (Unichain Sepolia, collateral-only) | same as the Unichain pool with `collateralOnly = true` |

`script/deploy.sh` performs the deployment in the required order (reactive first, then pools, then `setPools`, then funding).
The current addresses are in `deployments.env`, and the values can be read back from each contract (`raisePeriod()`,
`LOAN_PERIOD()`, `GRACE()`, `collateralOnly()`, `_SERVICE_PROVIDER()`, `_CALLBACK_SENDER()`).

## Runtime code hashes
```
cast codehash <address> --rpc-url <rpc>
```
Current values are listed in the README. The reactive contract's hash is stable across deployments because it has no immutables
that differ. Each pool's runtime code embeds immutables (`_SERVICE_PROVIDER`, `_CALLBACK_SENDER`, `LOAN_PERIOD`, `GRACE`,
`collateralOnly`), so two pools built from the same source have different hashes. To compare with a local build:

1. `forge build` and take `deployedBytecode.object` from `out/CatenaPool.sol/CatenaPool.json`.
2. Take the `immutableReferences` from the same artifact, which list the byte offsets of every immutable.
3. Zero those 32-byte ranges in both the local bytecode and the on-chain code (`cast code <address>`), then hash both.

## What was tried for verification
- **Sourcify** (`https://sourcify.dev/server/v2/verify/5318007/<address>`): the compile worker fails with "Failed fetching solc"
  for versions 0.8.29 and 0.8.30. The Omni library requires `^0.8.29`, so a lower compiler is not an option. This looks like a
  service-side problem, not a source mismatch, but we have not been able to confirm that with the Sourcify team.
- **Reactscan**: no verification API was found. Blockscout-style endpoints returned 404.
- **Next step if time allows**: ask the Reactive team whether they have a manual verification route.
