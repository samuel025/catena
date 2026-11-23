#!/usr/bin/env bash
# Capital efficiency: the same borrow is rejected by a collateral-only pool and approved on Unichain
# because of the wallet's Base history. Run script/demo.sh first so the main wallet has a tier.
set -euo pipefail; cd "$(dirname "$0")/.."
set -a; source .env; source deployments.env; set +a; source script/lib.sh
ME=$(cast wallet address --private-key "$PRIVATE_KEY"); AMT=20000000000000000000   # 20 units
show "$ME" "wallet"
echo "-- collateral-only pool on Unichain (no collateral posted):"
cast send "$POOL_UNI_COLL" 'borrow(uint256)' $AMT --rpc-url "$UNICHAIN_SEPOLIA_RPC" --private-key "$PRIVATE_KEY" 2>&1 | grep -iE "revert|QuotaExceeded|error" | head -2 | cut -c1-200 || true
echo "-- Catena pool on Unichain (limit comes from the Base repayment history):"
cast send "$POOL_UNI" 'borrow(uint256)' $AMT --rpc-url "$UNICHAIN_SEPOLIA_RPC" --private-key "$PRIVATE_KEY" 2>&1 | grep -E "^(status|transactionHash)"
cast send "$POOL_UNI" 'repay(uint256)' $AMT --rpc-url "$UNICHAIN_SEPOLIA_RPC" --private-key "$PRIVATE_KEY" 2>&1 | grep -E "^status"
