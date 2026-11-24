#!/usr/bin/env bash
# Thin-file wallet climbs: borrow+repay on Base, watch the quota arrive on Unichain. Needs deployments.env.
set -euo pipefail
cd "$(dirname "$0")/.."
script/check_funds.sh --require >/dev/null || { script/check_funds.sh --require; exit 1; }
set -a; source .env; source deployments.env; set +a
ACTOR_KEY=${ACTOR_KEY:-$PRIVATE_KEY}   # run as another wallet: ACTOR_KEY=0x... script/demo.sh
ME=$(cast wallet address --private-key "$ACTOR_KEY")
AMT=1000000000000000000   # 1 fake unit

q() { # chain rpc pool -> "quota version tier"
  echo "quota=$(cast call "$2" 'quotaOf(address)(uint256)' "$ME" --rpc-url "$1" | awk '{print $1}') version=$(cast call "$2" 'scoreVersion(address)(uint64)' "$ME" --rpc-url "$1")"
}
wait_version() { # rpc pool target
  for _ in $(seq 1 30); do
    v=$(cast call "$2" 'scoreVersion(address)(uint64)' "$ME" --rpc-url "$1"); [ "$v" -ge "$3" ] && return 0; sleep 3
  done; echo "timeout waiting for version $3"; return 1
}

round() { # n
  echo "== round $1"
  cast send "$POOL_BASE" "borrow(uint256)" $AMT --rpc-url "$BASE_SEPOLIA_RPC" --private-key "$ACTOR_KEY" | grep -E "^transactionHash" | sed 's/^/borrow  /'
  cast send "$POOL_BASE" "repay(uint256)" $AMT --rpc-url "$BASE_SEPOLIA_RPC" --private-key "$ACTOR_KEY" | grep -E "^transactionHash" | sed 's/^/repay   /'
  wait_version "$UNICHAIN_SEPOLIA_RPC" "$POOL_UNI" "$1"; wait_version "$BASE_SEPOLIA_RPC" "$POOL_BASE" "$1"
  echo "base:     $(q "$BASE_SEPOLIA_RPC" "$POOL_BASE")"
  echo "unichain: $(q "$UNICHAIN_SEPOLIA_RPC" "$POOL_UNI")"
  echo "passport: $(cast call "$REACTIVE" 'passports(address)(uint32,uint32,uint32,uint8,uint8,bool,uint8,uint16,uint64,uint64,uint64,uint256)' "$ME" --rpc-url "$LASNA_RPC" | tr '\n' ' ')"
}

echo "start    base: $(q "$BASE_SEPOLIA_RPC" "$POOL_BASE")  unichain: $(q "$UNICHAIN_SEPOLIA_RPC" "$POOL_UNI")"
START=$(cast call "$POOL_UNI" 'scoreVersion(address)(uint64)' "$ME" --rpc-url "$UNICHAIN_SEPOLIA_RPC")
round $((START+1))
echo "(waiting 62s so the next raise is allowed: one tier per period)"; sleep 62
round $((START+2))
