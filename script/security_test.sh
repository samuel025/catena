#!/usr/bin/env bash
# Double-draw test: draw the full quota on BOTH chains at once, then try to draw more. Fixed per-chain quotas
# bound total exposure by the total limit, whatever the callback latency. Run script/demo.sh first.
set -euo pipefail; cd "$(dirname "$0")/.."
script/check_funds.sh --require >/dev/null || { script/check_funds.sh --require; exit 1; }
set -a; source .env; source deployments.env; set +a; source script/lib.sh
ACTOR_KEY=${ACTOR_KEY:-$PRIVATE_KEY}   # run as another wallet: ACTOR_KEY=0x... script/security_test.sh
ME=$(cast wallet address --private-key "$ACTOR_KEY")
QB=$(quota_of "$BASE_SEPOLIA_RPC" "$POOL_BASE" "$ME"); QU=$(quota_of "$UNICHAIN_SEPOLIA_RPC" "$POOL_UNI" "$ME")
TIER=$(cast call "$REACTIVE" 'tierOf(address)(uint8)' "$ME" --rpc-url "$LASNA_RPC")
LIMIT=$(cast call "$REACTIVE" 'tierLimit(uint256)(uint256)' "$TIER" --rpc-url "$LASNA_RPC" | awk '{print $1}')
echo "quotas: base=$(eth $QB) unichain=$(eth $QU)  total limit at tier $TIER = $(eth $LIMIT)"
cast send "$POOL_BASE" 'borrow(uint256)' "$QB" --rpc-url "$BASE_SEPOLIA_RPC" --private-key "$ACTOR_KEY" >/tmp/sec_b.txt 2>&1 &
cast send "$POOL_UNI" 'borrow(uint256)' "$QU" --rpc-url "$UNICHAIN_SEPOLIA_RPC" --private-key "$ACTOR_KEY" >/tmp/sec_u.txt 2>&1 &
wait
echo "attempt 1 more on each chain (should revert):"
for c in "$BASE_SEPOLIA_RPC $POOL_BASE" "$UNICHAIN_SEPOLIA_RPC $POOL_UNI"; do set -- $c
  { cast send "$2" 'borrow(uint256)' 1 --rpc-url "$1" --private-key "$ACTOR_KEY" 2>&1 || true; } | { grep -ciE "revert|QuotaExceeded" || true; } | sed 's/^/  reverted (1 = yes): /'
done
OB=$(cast call "$POOL_BASE" 'owed(address)(uint256)' "$ME" --rpc-url "$BASE_SEPOLIA_RPC" | awk '{print $1}')
OU=$(cast call "$POOL_UNI" 'owed(address)(uint256)' "$ME" --rpc-url "$UNICHAIN_SEPOLIA_RPC" | awk '{print $1}')
TOTAL=$(python3 -I -c "print($OB+$OU)")
echo "owed: base=$(eth $OB) unichain=$(eth $OU) total=$(eth $TOTAL)  limit=$(eth $LIMIT)"
python3 -I -c "import sys; sys.exit(0 if $TOTAL <= $LIMIT else 1)" && echo "PASS: total exposure within total limit" || { echo "FAIL"; exit 1; }
# clean up so the wallet can be reused
cast send "$POOL_BASE" 'repay(uint256)' "$OB" --rpc-url "$BASE_SEPOLIA_RPC" --private-key "$ACTOR_KEY" >/dev/null 2>&1 || true
cast send "$POOL_UNI" 'repay(uint256)' "$OU" --rpc-url "$UNICHAIN_SEPOLIA_RPC" --private-key "$ACTOR_KEY" >/dev/null 2>&1 || true
