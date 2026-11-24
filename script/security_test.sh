#!/usr/bin/env bash
# Double-draw test: draw the full quota on BOTH chains at once, then try to draw more. Fixed per-chain quotas
# bound total exposure by the total limit, whatever the callback latency. Run script/demo.sh first.
set -euo pipefail; cd "$(dirname "$0")/.."
script/check_funds.sh --require >/dev/null || { script/check_funds.sh --require; exit 1; }
set -a; source .env; source deployments.env; set +a; source script/lib.sh
ACTOR_KEY=${ACTOR_KEY:-$PRIVATE_KEY}   # run as another wallet: ACTOR_KEY=0x... script/security_test.sh
ME=$(cast wallet address --private-key "$ACTOR_KEY")
lim() { cast call "$2" 'borrowLimit(address)(uint256)' "$ME" --rpc-url "$1" | awk '{print $1}'; }
col() { cast call "$2" 'collateral(address)(uint256)' "$ME" --rpc-url "$1" | awk '{print $1}'; }
QB=$(lim "$BASE_SEPOLIA_RPC" "$POOL_BASE"); QU=$(lim "$UNICHAIN_SEPOLIA_RPC" "$POOL_UNI")   # per-chain limit = quota + secured top-up
SEC=$(python3 -I -c "print(($(col "$BASE_SEPOLIA_RPC" "$POOL_BASE")+$(col "$UNICHAIN_SEPOLIA_RPC" "$POOL_UNI"))//2)")   # collateral/2, if the wallet posted any
TIER=$(cast call "$REACTIVE" 'tierOf(address)(uint8)' "$ME" --rpc-url "$LASNA_RPC")
LIMIT=$(cast call "$REACTIVE" 'tierLimit(uint256)(uint256)' "$TIER" --rpc-url "$LASNA_RPC" | awk '{print $1}')
echo "per-chain limits: base=$(eth $QB) unichain=$(eth $QU)  total limit at tier $TIER = $(eth $LIMIT)  (+ secured $(eth $SEC) from own collateral)"
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
BOUND=$(python3 -I -c "print($LIMIT+$SEC)")
echo "owed: base=$(eth $OB) unichain=$(eth $OU) total=$(eth $TOTAL)  bound=$(eth $BOUND)"
python3 -I -c "import sys; sys.exit(0 if $TOTAL <= $BOUND else 1)" && echo "PASS: total exposure within the total limit plus own collateral" || { echo "FAIL"; exit 1; }
# clean up so the wallet can be reused
cast send "$POOL_BASE" 'repay(uint256)' "$OB" --rpc-url "$BASE_SEPOLIA_RPC" --private-key "$ACTOR_KEY" >/dev/null 2>&1 || true
cast send "$POOL_UNI" 'repay(uint256)' "$OU" --rpc-url "$UNICHAIN_SEPOLIA_RPC" --private-key "$ACTOR_KEY" >/dev/null 2>&1 || true
