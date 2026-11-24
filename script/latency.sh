#!/usr/bin/env bash
# Measures origin event -> reactive tx -> destination callbacks, from chain block timestamps (1 s resolution).
# Usage: script/latency.sh [rounds]   Costs about 0.04 lREACT per round.
set -euo pipefail; cd "$(dirname "$0")/.."
script/check_funds.sh --require >/dev/null || { script/check_funds.sh --require; exit 1; }
set -a; source .env; source deployments.env; set +a; source script/lib.sh
SYS=0x8888888888888888888888888888888888888888
ROUNDS=${1:-4}; AMT=1000000000000000000
new_wallet LAT
TOPIC="0x000000000000000000000000$(echo ${REACTIVE#0x} | tr 'A-F' 'a-f')"
CBREQ=0xef94dbc611c4b95bf4b8ba34b413972180c2faf26fbb480befacedd83e07b133
QSET=$(cast keccak "QuotaSet(address,uint256,uint64)")
ts() { cast block "$2" --rpc-url "$1" -f timestamp; }
logs() { # rpc json-filter -> first blockNumber (decimal) of matching log, else empty
  cast rpc eth_getLogs "$2" --rpc-url "$1" | python3 -I -c 'import json,sys; d=json.load(sys.stdin); print(int(d[0]["blockNumber"],16) if d else "")'
}
hex() { printf '0x%x' "$1"; }
echo "(timestamps have 1 s resolution and chains' clocks differ, so a column can read about 1 s off; negative origin->reactive means under 1 s)"
echo "round | origin->reactive | reactive->Base cb | reactive->Unichain cb | total to Base | total to Unichain   (seconds)"
sumB=0; sumU=0; sumR=0; n=0
for i in $(seq 1 "$ROUNDS"); do
  v0=$(version_of "$BASE_SEPOLIA_RPC" "$POOL_BASE" "$LAT_ADDR")
  cast send "$POOL_BASE" 'borrow(uint256)' $AMT --rpc-url "$BASE_SEPOLIA_RPC" --private-key "$LAT_KEY" >/dev/null
  sleep 6   # let the Borrowed react settle so it cannot be mistaken for the Repaid one
  v0=$(version_of "$BASE_SEPOLIA_RPC" "$POOL_BASE" "$LAT_ADDR")
  H0=$(cast block-number --rpc-url "$LASNA_RPC"); UH0=$(cast block-number --rpc-url "$UNICHAIN_SEPOLIA_RPC")
  RB=$(cast send "$POOL_BASE" 'repay(uint256)' $AMT --rpc-url "$BASE_SEPOLIA_RPC" --private-key "$LAT_KEY" --json | python3 -I -c 'import json,sys; print(int(json.load(sys.stdin)["blockNumber"],16))')
  wait_version "$BASE_SEPOLIA_RPC" "$POOL_BASE" "$LAT_ADDR" $((v0+1)); wait_version "$UNICHAIN_SEPOLIA_RPC" "$POOL_UNI" "$LAT_ADDR" $((v0+1))
  T_O=$(ts "$BASE_SEPOLIA_RPC" "$RB")
  LB=$(logs "$LASNA_RPC" "{\"address\":\"$SYS\",\"fromBlock\":\"$(hex $((H0-5)))\",\"toBlock\":\"latest\",\"topics\":[\"$CBREQ\",null,\"$TOPIC\"]}")
  T_R=$(ts "$LASNA_RPC" "$LB")
  BH=$(cast block-number --rpc-url "$BASE_SEPOLIA_RPC"); BTO=$(( RB+190 < BH ? RB+190 : BH ))   # public RPC: max 200-block range
  BB=$(logs "$BASE_SEPOLIA_RPC" "{\"address\":\"$POOL_BASE\",\"fromBlock\":\"$(hex $RB)\",\"toBlock\":\"$(hex $BTO)\",\"topics\":[\"$QSET\"]}")
  UB=$(logs "$UNICHAIN_SEPOLIA_RPC" "{\"address\":\"$POOL_UNI\",\"fromBlock\":\"$(hex $UH0)\",\"toBlock\":\"latest\",\"topics\":[\"$QSET\"]}")
  T_B=$(ts "$BASE_SEPOLIA_RPC" "$BB"); T_U=$(ts "$UNICHAIN_SEPOLIA_RPC" "$UB")
  echo "$i | $((T_R-T_O)) | $((T_B-T_R)) | $((T_U-T_R)) | $((T_B-T_O)) | $((T_U-T_O))"
  sumR=$((sumR+T_R-T_O)); sumB=$((sumB+T_B-T_O)); sumU=$((sumU+T_U-T_O)); n=$((n+1))
done
python3 -I -c "print(f'mean over $n rounds: origin->reactive {$sumR/$n:.1f}s, total to Base {$sumB/$n:.1f}s, total to Unichain {$sumU/$n:.1f}s')"
