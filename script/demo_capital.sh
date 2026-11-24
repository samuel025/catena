#!/usr/bin/env bash
# Capital efficiency: the same borrow is rejected by a collateral-only pool and approved on Unichain
# because of the wallet's Base history. Run script/demo.sh first so the main wallet has a tier.
set -euo pipefail; cd "$(dirname "$0")/.."
script/check_funds.sh --require >/dev/null || { script/check_funds.sh --require; exit 1; }
set -a; source .env; source deployments.env; set +a; source script/lib.sh
ACTOR_KEY=${ACTOR_KEY:-$PRIVATE_KEY}   # run as another wallet: ACTOR_KEY=0x... script/demo_capital.sh
ME=$(cast wallet address --private-key "$ACTOR_KEY"); AMT=20000000000000000000   # 20 units
show "$ME" "wallet"
echo "-- collateral-only pool on Unichain (no collateral posted):"
cast send "$POOL_UNI_COLL" 'borrow(uint256)' $AMT --rpc-url "$UNICHAIN_SEPOLIA_RPC" --private-key "$ACTOR_KEY" 2>&1 | grep -iE "revert|QuotaExceeded|error" | head -2 | cut -c1-200 || true
echo "-- Catena pool on Unichain (limit comes from the Base repayment history):"
cast send "$POOL_UNI" 'borrow(uint256)' $AMT --rpc-url "$UNICHAIN_SEPOLIA_RPC" --private-key "$ACTOR_KEY" 2>&1 | grep -E "^(status|transactionHash)"
sleep 4   # public RPCs can lag a block behind on nonce
cast send "$POOL_UNI" 'repay(uint256)' $AMT --rpc-url "$UNICHAIN_SEPOLIA_RPC" --private-key "$ACTOR_KEY" 2>&1 | grep -E "^status" || echo "(repay not confirmed yet; check owed)"
sleep 4
echo "-- same borrower, same collateral, two pools (amounts in wei; collateral is real testnet ETH, quotas are whole units)"
Q=$(quota_of "$UNICHAIN_SEPOLIA_RPC" "$POOL_UNI" "$ME"); EXTRA=50000000000000; OVER=$(python3 -I -c "print($Q+$EXTRA)")
lim() { cast call "$1" 'borrowLimit(address)(uint256)' "$ME" --rpc-url "$UNICHAIN_SEPOLIA_RPC" | awk '{print $1}'; }
cast send "$POOL_UNI_COLL" 'depositCollateral()' --value 0.0001ether --rpc-url "$UNICHAIN_SEPOLIA_RPC" --private-key "$ACTOR_KEY" 2>&1 | grep -E "^status"
sleep 4
cast send "$POOL_UNI" 'depositCollateral()' --value 0.0001ether --rpc-url "$UNICHAIN_SEPOLIA_RPC" --private-key "$ACTOR_KEY" 2>&1 | grep -E "^status"
sleep 4
echo "collateral posted in each pool: 0.0001 ETH"
echo "  collateral-only pool limit: $(lim "$POOL_UNI_COLL")   (half the collateral)"
echo "  Catena pool limit:          $(lim "$POOL_UNI")   (history quota $Q + half the collateral)"
echo "-- asking for the Catena limit ($OVER) from each pool:"
cast send "$POOL_UNI_COLL" 'borrow(uint256)' "$OVER" --rpc-url "$UNICHAIN_SEPOLIA_RPC" --private-key "$ACTOR_KEY" 2>&1 | grep -iE "revert|QuotaExceeded|error" | head -1 | cut -c1-120 || true
sleep 4
cast send "$POOL_UNI" 'borrow(uint256)' "$OVER" --rpc-url "$UNICHAIN_SEPOLIA_RPC" --private-key "$ACTOR_KEY" 2>&1 | grep -E "^status"
sleep 4
cast send "$POOL_UNI" 'repay(uint256)' "$OVER" --rpc-url "$UNICHAIN_SEPOLIA_RPC" --private-key "$ACTOR_KEY" 2>&1 | grep -E "^status" || echo "(repay not confirmed yet)"
