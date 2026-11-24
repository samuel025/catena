#!/usr/bin/env bash
# Records one full loop with every transaction hash: origin event on Base -> reactive tx on Lasna -> callbacks on
# Base and Unichain. Prints markdown with explorer links. Costs about 0.06 lREACT. Usage: script/trace_loop.sh > out.md
set -euo pipefail; cd "$(dirname "$0")/.."
script/check_funds.sh --require >/dev/null || { script/check_funds.sh --require >&2; exit 1; }
set -a; source .env; source deployments.env; set +a; source script/lib.sh
SYS=0x8888888888888888888888888888888888888888; AMT=1000000000000000000
new_wallet TRC >&2
TOPIC="0x000000000000000000000000$(echo ${REACTIVE#0x} | tr 'A-F' 'a-f')"
CBREQ=0xef94dbc611c4b95bf4b8ba34b413972180c2faf26fbb480befacedd83e07b133
QSET=$(cast keccak "QuotaSet(address,uint256,uint64)")
hex() { printf '0x%x' "$1"; }
txof() { # rpc filter -> first matching log's transactionHash
  cast rpc eth_getLogs "$2" --rpc-url "$1" | python3 -I -c 'import json,sys; d=json.load(sys.stdin); print(d[0]["transactionHash"] if d else "")'
}
jfield() { python3 -I -c "import json,sys; print(json.load(sys.stdin)['$1'])"; }
BORROW=$(cast send "$POOL_BASE" 'borrow(uint256)' $AMT --rpc-url "$BASE_SEPOLIA_RPC" --private-key "$TRC_KEY" --json | jfield transactionHash)
sleep 8
H0=$(cast block-number --rpc-url "$LASNA_RPC"); UH0=$(cast block-number --rpc-url "$UNICHAIN_SEPOLIA_RPC")
v0=$(version_of "$BASE_SEPOLIA_RPC" "$POOL_BASE" "$TRC_ADDR")
RJ=$(cast send "$POOL_BASE" 'repay(uint256)' $AMT --rpc-url "$BASE_SEPOLIA_RPC" --private-key "$TRC_KEY" --json)
REPAY=$(echo "$RJ" | jfield transactionHash); RB=$(echo "$RJ" | python3 -I -c 'import json,sys; print(int(json.load(sys.stdin)["blockNumber"],16))')
wait_version "$BASE_SEPOLIA_RPC" "$POOL_BASE" "$TRC_ADDR" $((v0+1)) >&2; wait_version "$UNICHAIN_SEPOLIA_RPC" "$POOL_UNI" "$TRC_ADDR" $((v0+1)) >&2
REACTIVE_TX=$(txof "$LASNA_RPC" "{\"address\":\"$SYS\",\"fromBlock\":\"$(hex $((H0-5)))\",\"toBlock\":\"latest\",\"topics\":[\"$CBREQ\",null,\"$TOPIC\"]}")
BH=$(cast block-number --rpc-url "$BASE_SEPOLIA_RPC"); BTO=$(( RB+190 < BH ? RB+190 : BH ))
CB_BASE=$(txof "$BASE_SEPOLIA_RPC" "{\"address\":\"$POOL_BASE\",\"fromBlock\":\"$(hex $RB)\",\"toBlock\":\"$(hex $BTO)\",\"topics\":[\"$QSET\"]}")
CB_UNI=$(txof "$UNICHAIN_SEPOLIA_RPC" "{\"address\":\"$POOL_UNI\",\"fromBlock\":\"$(hex $UH0)\",\"toBlock\":\"latest\",\"topics\":[\"$QSET\"]}")
echo "Wallet \`$TRC_ADDR\` borrowed 1 unit on Base Sepolia, then repaid it on time."
echo
echo "| Step | Chain | Transaction |"
echo "|---|---|---|"
echo "| 1. Borrowed event (origin) | Base Sepolia | [$BORROW](https://sepolia.basescan.org/tx/$BORROW) |"
echo "| 2. Repaid event (origin) | Base Sepolia | [$REPAY](https://sepolia.basescan.org/tx/$REPAY) |"
echo "| 3. Reactive transaction: update passport, run MLP, request callbacks | Lasna | [$REACTIVE_TX](https://lasna.reactscan.net/tx/$REACTIVE_TX) |"
echo "| 4. Callback: quota set | Base Sepolia | [$CB_BASE](https://sepolia.basescan.org/tx/$CB_BASE) |"
echo "| 5. Callback: quota set | Unichain Sepolia | [$CB_UNI](https://sepolia.uniscan.xyz/tx/$CB_UNI) |"
