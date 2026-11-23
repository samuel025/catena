# Shared helpers for demo scripts. Source after .env and deployments.env.
quota_of() { cast call "$2" 'quotaOf(address)(uint256)' "$3" --rpc-url "$1" | awk '{print $1}'; }
version_of() { cast call "$2" 'scoreVersion(address)(uint64)' "$3" --rpc-url "$1"; }
eth() { python3 -I -c "print(int('$1')/10**18)"; }
wait_version() { # rpc pool wallet target
  for _ in $(seq 1 40); do v=$(version_of "$1" "$2" "$3"); [ "$v" -ge "$4" ] && return 0; sleep 3; done
  echo "timeout waiting for version $4 on $2"; return 1
}
show() { # wallet label
  echo "$2: base quota=$(eth "$(quota_of "$BASE_SEPOLIA_RPC" "$POOL_BASE" "$1")")  unichain quota=$(eth "$(quota_of "$UNICHAIN_SEPOLIA_RPC" "$POOL_UNI" "$1")")  tier=$(cast call "$REACTIVE" 'tierOf(address)(uint8)' "$1" --rpc-url "$LASNA_RPC")  reasons=$(cast call "$REACTIVE" 'reasons(address)(uint8,uint8,int16,int16,bool)' "$1" --rpc-url "$LASNA_RPC" | tr '\n' ' ')"
}
# ephemeral demo wallet funded with a little Base gas from the main key
new_wallet() { # name -> sets ${name}_KEY / ${name}_ADDR and saves to .demo-wallets.env
  local out; out=$(cast wallet new)
  local addr key; addr=$(echo "$out" | awk '/Address/ {print $2}'); key=$(echo "$out" | awk '/Private key/ {print $3}')
  echo "${1}_ADDR=$addr" >> .demo-wallets.env; echo "${1}_KEY=$key" >> .demo-wallets.env
  cast send "$addr" --value 0.0004ether --rpc-url "$BASE_SEPOLIA_RPC" --private-key "$PRIVATE_KEY" >/dev/null
  eval "${1}_ADDR=$addr; ${1}_KEY=$key"
}
