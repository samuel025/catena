#!/usr/bin/env bash
# Creates a fresh demo wallet funded with gas on Base and Unichain. Prints an ACTOR_KEY line to export.
set -euo pipefail; cd "$(dirname "$0")/.."
set -a; source .env; source deployments.env; set +a; source script/lib.sh
new_wallet ACTOR
echo "wallet: $ACTOR_ADDR"; echo "export ACTOR_KEY=$ACTOR_KEY   # then: script/demo.sh, demo_capital.sh, security_test.sh run as this wallet"
echo "open web/index.html?w=$ACTOR_ADDR"
