#!/usr/bin/env bash
# Thin-file wallet (slow capped climb) and defaulter (quotas drop to zero on both chains, hard rule).
set -euo pipefail; cd "$(dirname "$0")/.."
script/check_funds.sh --require >/dev/null || { script/check_funds.sh --require; exit 1; }
set -a; source .env; source deployments.env; set +a; source script/lib.sh
AMT=1000000000000000000
tx() { cast send "$@" 2>&1 | grep -E "^transactionHash" | awk '{print $2}'; }

echo "=== Thin-file wallet: two repayments seconds apart, but only one tier per period"
new_wallet THIN
v0=$(version_of "$BASE_SEPOLIA_RPC" "$POOL_BASE" "$THIN_ADDR")
echo "borrow 2   $(tx "$POOL_BASE" 'borrow(uint256)' 2000000000000000000 --rpc-url "$BASE_SEPOLIA_RPC" --private-key "$THIN_KEY")"
echo "repay 1    $(tx "$POOL_BASE" 'repay(uint256)' 1000000000000000000 --rpc-url "$BASE_SEPOLIA_RPC" --private-key "$THIN_KEY")"
echo "repay 1    $(tx "$POOL_BASE" 'repay(uint256)' 1000000000000000000 --rpc-url "$BASE_SEPOLIA_RPC" --private-key "$THIN_KEY")"
wait_version "$BASE_SEPOLIA_RPC" "$POOL_BASE" "$THIN_ADDR" $((v0+2)); wait_version "$UNICHAIN_SEPOLIA_RPC" "$POOL_UNI" "$THIN_ADDR" $((v0+2))
show "$THIN_ADDR" "after two quick repayments (model may qualify for tier 2, held at 1 by the period rule)"

echo; echo "=== Defaulter: one good repayment, then a loan left unpaid"
new_wallet DEF
echo "borrow $(tx "$POOL_BASE" 'borrow(uint256)' $AMT --rpc-url "$BASE_SEPOLIA_RPC" --private-key "$DEF_KEY")"
echo "repay  $(tx "$POOL_BASE" 'repay(uint256)' $AMT --rpc-url "$BASE_SEPOLIA_RPC" --private-key "$DEF_KEY")"
wait_version "$UNICHAIN_SEPOLIA_RPC" "$POOL_UNI" "$DEF_ADDR" 1; show "$DEF_ADDR" "good standing"
echo "borrow $(tx "$POOL_BASE" 'borrow(uint256)' $AMT --rpc-url "$BASE_SEPOLIA_RPC" --private-key "$DEF_KEY")"
DUE=$(cast call "$POOL_BASE" 'dueAt(address)(uint256)' "$DEF_ADDR" --rpc-url "$BASE_SEPOLIA_RPC" | awk '{print $1}')
GR=$(cast call "$POOL_BASE" 'GRACE()(uint256)' --rpc-url "$BASE_SEPOLIA_RPC" | awk '{print $1}')
echo "...loan unpaid; waiting for due + grace"
while [ "$(cast block latest --rpc-url "$BASE_SEPOLIA_RPC" -f timestamp)" -le $((DUE+GR)) ]; do sleep 5; done
echo "markDefault $(tx "$POOL_BASE" 'markDefault(address)' "$DEF_ADDR" --rpc-url "$BASE_SEPOLIA_RPC" --private-key "$PRIVATE_KEY")"
wait_version "$UNICHAIN_SEPOLIA_RPC" "$POOL_UNI" "$DEF_ADDR" 2; wait_version "$BASE_SEPOLIA_RPC" "$POOL_BASE" "$DEF_ADDR" 2
show "$DEF_ADDR" "after default (reason 7 = default rule)"
