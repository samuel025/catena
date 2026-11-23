#!/usr/bin/env bash
# Deploys the Catena loop. Order matters: the pools' callback sender is immutable.
#   1. reactive contract on Lasna   2. pools on both chains   3. setPools (subscribes)   4. fund callbacks
set -euo pipefail
cd "$(dirname "$0")/.."
source .env

LASNA_ID=5318007; BASE_ID=84532; UNI_ID=1301
BASE_PROXY=0x476F44b11F5C942c58f4c8E3d0300E5710743585
UNI_PROXY=0x775c9B990ADe401060B78D0e98684eEf8d2466C1
REACTIVE_FUND=${REACTIVE_FUND:-0.5ether}   # lREACT for react() fees
POOL_FUND=${POOL_FUND:-0.01ether}          # native gas for each pool's callbacks
LOAN_PERIOD=${LOAN_PERIOD:-60}             # demo values: a loan is due in 60s, default may be flagged 30s later
GRACE=${GRACE:-30}

create() { # rpc chainid value contract [ctor args...]
  local rpc=$1 id=$2 val=$3 c=$4; shift 4
  if [ $# -gt 0 ]; then args=(--constructor-args "$@"); else args=(); fi
  forge create "$c" --broadcast --rpc-url "$rpc" --chain-id "$id" --private-key "$PRIVATE_KEY" \
    --value "$val" "${args[@]}" | awk '/Deployed to:/ {print $3}'
}

echo "1/4 reactive contract on Lasna"
REACTIVE=$(create "$LASNA_RPC" $LASNA_ID "$REACTIVE_FUND" src/CatenaReactive.sol:CatenaReactive "${RAISE_PERIOD:-60}")
echo "  CatenaReactive: $REACTIVE"

echo "2/4 pools"
POOL_BASE=$(create "$BASE_SEPOLIA_RPC" $BASE_ID "$POOL_FUND" src/CatenaPool.sol:CatenaPool "$BASE_PROXY" "$REACTIVE" false "$LOAN_PERIOD" "$GRACE")
POOL_UNI=$(create "$UNICHAIN_SEPOLIA_RPC" $UNI_ID "$POOL_FUND" src/CatenaPool.sol:CatenaPool "$UNI_PROXY" "$REACTIVE" false "$LOAN_PERIOD" "$GRACE")
# collateral-only pool: the demo's "before" case. Not registered with the reactive contract, so it never gets quotas.
POOL_UNI_COLL=$(create "$UNICHAIN_SEPOLIA_RPC" $UNI_ID 0 src/CatenaPool.sol:CatenaPool "$UNI_PROXY" "$REACTIVE" true "$LOAN_PERIOD" "$GRACE")
echo "  Unichain collateral-only pool: $POOL_UNI_COLL"
echo "  Base pool: $POOL_BASE"; echo "  Unichain pool: $POOL_UNI"

echo "3/4 setPools (subscribes to pool events)"
cast send "$REACTIVE" "setPools(uint256[],address[])" "[$BASE_ID,$UNI_ID]" "[$POOL_BASE,$POOL_UNI]" \
  --rpc-url "$LASNA_RPC" --private-key "$PRIVATE_KEY"

echo "4/4 fund callbacks via each proxy's depositTo (reserves are spent before debt accrues)"
cast send "$BASE_PROXY" "depositTo(address)" "$POOL_BASE" --value "$POOL_FUND" --rpc-url "$BASE_SEPOLIA_RPC" --private-key "$PRIVATE_KEY"
cast send "$UNI_PROXY" "depositTo(address)" "$POOL_UNI" --value "$POOL_FUND" --rpc-url "$UNICHAIN_SEPOLIA_RPC" --private-key "$PRIVATE_KEY"

cat > deployments.env <<EOF
REACTIVE=$REACTIVE
POOL_BASE=$POOL_BASE
POOL_UNI=$POOL_UNI
POOL_UNI_COLL=$POOL_UNI_COLL
EOF
echo "saved deployments.env"
