#!/usr/bin/env bash
# Funding check: the reactive contract and each pool must have reserves and zero debt, or events/callbacks stop.
set -euo pipefail; cd "$(dirname "$0")/.."
set -a; source .env; source deployments.env; set +a
SYS=0x8888888888888888888888888888888888888888
BASE_PROXY=0x476F44b11F5C942c58f4c8E3d0300E5710743585; UNI_PROXY=0x775c9B990ADe401060B78D0e98684eEf8d2466C1
e() { python3 -I -c "print(f'{int(\"$1\".split()[0])/1e18:.4f}')"; }
row() { echo "$1: reserves=$(e "$(cast call "$3" 'reserves(address)(uint256)' "$4" --rpc-url "$2")") debt=$(e "$(cast call "$3" 'debt(address)(uint256)' "$4" --rpc-url "$2")") balance=$(cast balance "$4" --rpc-url "$2" --ether | tail -1 | cut -c1-8)"; }
row "reactive (lREACT, Lasna)   " "$LASNA_RPC" $SYS "$REACTIVE"
row "base pool (ETH)            " "$BASE_SEPOLIA_RPC" $BASE_PROXY "$POOL_BASE"
row "unichain pool (ETH)        " "$UNICHAIN_SEPOLIA_RPC" $UNI_PROXY "$POOL_UNI"
echo "rule of thumb: ~0.03 lREACT per reactive tx at 100 gwei (every pool event, incl. Borrowed, triggers one)"
