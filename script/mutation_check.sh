#!/usr/bin/env bash
# Mutation check: break one safety rule at a time and confirm the test suite fails.
# Works on a throwaway copy of src/ and test/, so the repository is never modified.
# Run: script/mutation_check.sh                                   (whole suite)
#      ONLY=test/Invariant.t.sol script/mutation_check.sh          (one test file)
set -euo pipefail; cd "$(dirname "$0")/.."
ROOT=$PWD
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
cp -r src test foundry.toml "$WORK"/; ln -s "$ROOT/lib" "$WORK/lib"; mkdir -p "$WORK/model"; cp model/*.json "$WORK/model/" 2>/dev/null || true

# file | exact text | replacement | what the mutation breaks
MUTANTS=(
  "src/CatenaPool.sol|if (version <= scoreVersion[borrower]) return;|// mutated|stale callbacks overwrite newer quotas"
  "src/CatenaPool.sol|(defaultFlagged[borrower] ? 0 : quotaOf(borrower))|quotaOf(borrower)|a local default flag no longer removes unsecured credit"
  "src/CatenaPool.sol|if (defaultFlagged[borrower] && owed[borrower] > 0) return 0;|// mutated|a defaulter who still owes can borrow against collateral"
  "src/CatenaPool.sol|if (newOwed > limit)|if (newOwed > limit + 1 ether)|the pool lends past the limit"
  "src/CatenaReactive.sol|if (p.defaulted) return 0;|// mutated|the default rule stops forcing tier 0"
  "src/CatenaReactive.sol|return p.tier + 1;|return modelTier;|raises skip the one-tier-per-period climb"
  "src/CatenaReactive.sol|uint256 quotaEach = p.defaulted ? 0 :|uint256 quotaEach =|callbacks give defaulters the tier-0 quota"
  "src/CatenaReactive.sol|if (seen[key]) return;|// mutated|duplicate events are counted twice"
  "src/CatenaReactive.sol|int256(uint256(p.late) * 1024 / tot)|int256(uint256(on) * 1024 / tot)|the late-ratio input is inverted, breaking monotonicity"
)

caught=0; missed=0
for m in "${MUTANTS[@]}"; do
  IFS='|' read -r file from to why <<<"$m"
  cp "$ROOT/$file" "$WORK/$file"
  n=$(grep -cF -- "$from" "$WORK/$file" || true)
  if [ "$n" != 1 ]; then echo "SETUP ERROR: '$from' found $n times in $file"; exit 2; fi
  python3 - "$WORK/$file" "$from" "$to" <<'PY'
import sys; p, a, b = sys.argv[1:]; s = open(p).read(); open(p, "w").write(s.replace(a, b, 1))
PY
  if (cd "$WORK" && forge test -q ${ONLY:+--match-path "$ONLY"} >/dev/null 2>&1); then
    echo "MISSED  $why"; missed=$((missed + 1))
  else
    echo "caught  $why"; caught=$((caught + 1))
  fi
  cp "$ROOT/$file" "$WORK/$file"
done
echo "$caught caught, $missed missed"
[ "$missed" = 0 ]
