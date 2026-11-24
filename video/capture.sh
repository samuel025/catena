#!/usr/bin/env bash
# Captures a real run for the demo video: command output (secrets filtered) and dashboard screenshots.
# One process at a time, low priority, so a laptop stays responsive. Output dir: $1 (default video/work).
# Costs about 1 lREACT. Needs the page served: (cd web && python3 -m http.server 8080)
set -euo pipefail; cd "$(dirname "$0")/.."
W=${1:-video/work}; mkdir -p "$W"
set -a; source .env; source deployments.env; set +a; source script/lib.sh
N="nice -n 19 ionice -c3"
clean() { { grep -v -i "private\|_KEY\|mnemonic" || true; }; }
shot() { # name wallet  -> full-page screenshot of the dashboard
  $N google-chrome --headless=new --no-sandbox --disable-gpu --hide-scrollbars --window-size=1280,2950 \
    --virtual-time-budget=18000 --screenshot="$W/$1.png" "http://localhost:8080/index.html?w=$2" >/dev/null 2>&1
  pkill -x chrome 2>/dev/null || true; sleep 1
}
$N script/check_funds.sh --require >/dev/null
echo "== hero wallet"
eval "$($N script/new_actor.sh 2>&1 | grep '^export' | sed 's/ *#.*//')"; ME=$(cast wallet address --private-key "$ACTOR_KEY")
echo "$ME" > "$W/hero.addr"
shot s0_before "$ME"
{
  echo "\$ cast send \$POOL_UNI_COLL 'borrow(uint256)' 20e18   # collateral-only pool, fresh wallet"
  cast send "$POOL_UNI_COLL" 'borrow(uint256)' 20000000000000000000 --rpc-url "$UNICHAIN_SEPOLIA_RPC" --private-key "$ACTOR_KEY" 2>&1 | { grep -iE "revert|error" || true; } | sed -n '1p' | cut -c1-150 || true
  echo "\$ cast send \$POOL_UNI 'borrow(uint256)' 20e18         # Catena pool, no history yet (starter quota 2)"
  cast send "$POOL_UNI" 'borrow(uint256)' 20000000000000000000 --rpc-url "$UNICHAIN_SEPOLIA_RPC" --private-key "$ACTOR_KEY" 2>&1 | { grep -iE "revert|error" || true; } | sed -n '1p' | cut -c1-150 || true
} 2>&1 | clean > "$W/t1_before.txt"
echo "== demo.sh"; $N script/demo.sh 2>&1 | clean > "$W/t2_demo.txt"
shot s2_after "$ME"
echo "== demo_capital.sh"; $N script/demo_capital.sh 2>&1 | clean > "$W/t3_capital.txt"
sleep 5; shot s3_capital "$ME"
echo "== second wallet + security"
eval "$($N script/new_actor.sh 2>&1 | grep '^export' | sed 's/ *#.*//')"
$N script/demo.sh >/dev/null 2>&1
$N script/security_test.sh 2>&1 | clean > "$W/t4_security.txt"
echo "== defaulter"; $N script/demo_wallets.sh 2>&1 | clean > "$W/t5_wallets.txt"
D=$(grep '^DEF_ADDR' .demo-wallets.env | tail -1 | cut -d= -f2); echo "$D" > "$W/def.addr"
shot s4_defaulter "$D"
echo "== done"
