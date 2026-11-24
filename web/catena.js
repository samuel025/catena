// Chain-reading logic, kept free of DOM and of any import so it can run in a browser or in Node (tests).
export const TIER_THRESHOLDS = [307, 563, 819]; // must match model/train.py
export const SCORE_MAX = 1024;

const REACTIVE_ABI = [
  "function passports(address) view returns (uint32 onTime,uint32 late,uint32 streak,uint8 recentLate,uint8 recentCount,bool defaulted,uint8 tier,uint16 score,uint64 version,uint64 firstSeen,uint64 lastRaiseAt,uint256 debt)",
  "function reasons(address) view returns (uint8 helped,uint8 hurt,int16 helpedDelta,int16 hurtDelta,bool set)",
  "function tierLimit(uint256) view returns (uint256)",
  "event Scored(address indexed borrower,uint16 score,uint8 tier,uint64 version)",
];
const POOL_ABI = [
  "function quotaOf(address) view returns (uint256)",
  "function scoreVersion(address) view returns (uint64)",
  "function owed(address) view returns (uint256)",
];

// Feature ids match CatenaReactive: 6 = none, 7 = default rule.
const HELPED = ["on-time repayments", "few or no late payments", "consistent recent repayments", "low outstanding debt", "a long history", "a recent on-time streak"];
const HURT = ["few on-time repayments so far", "late payments", "inconsistent recent repayments", "high outstanding debt", "a short history", "a short on-time streak"];

export function explain(r) {
  if (!r.set) return { helped: null, hurt: null, note: "No tier change yet, so no reasons recorded." };
  const helped = r.helped < 6 ? `${HELPED[r.helped]} (+${r.helpedDelta})` : null;
  let hurt = null;
  if (r.hurt === 7) hurt = "a default (hard rule, not the model)";
  else if (r.hurt < 6) hurt = `${HURT[r.hurt]} (${r.hurtDelta})`;
  return { helped, hurt, note: "Model sensitivity versus a typical borrower, not the definitive reason." };
}

export function tierFromScore(s) {
  return TIER_THRESHOLDS.filter((t) => s >= t).length;
}

export function makeReader(ethers, cfg) {
  const prov = (c) => new ethers.JsonRpcProvider(c.rpc, undefined, { staticNetwork: true, batchMaxCount: 1 });
  const lasna = prov(cfg.chains.lasna), base = prov(cfg.chains.base), uni = prov(cfg.chains.unichain);
  const reactive = new ethers.Contract(cfg.reactive, REACTIVE_ABI, lasna);
  const poolBase = new ethers.Contract(cfg.chains.base.pool, POOL_ABI, base);
  const poolUni = new ethers.Contract(cfg.chains.unichain.pool, POOL_ABI, uni);

  async function readWallet(addr) {
    const [p, r, qb, qu, vb, vu, ob, ou] = await Promise.all([
      reactive.passports(addr), reactive.reasons(addr),
      poolBase.quotaOf(addr), poolUni.quotaOf(addr),
      poolBase.scoreVersion(addr), poolUni.scoreVersion(addr),
      poolBase.owed(addr), poolUni.owed(addr),
    ]);
    const limit = await reactive.tierLimit(p.tier);
    const unit = 10n ** 18n;
    const n = (x) => Number(x / (unit / 100n)) / 100; // whole units with 2 decimals
    return {
      tier: Number(p.tier), score: Number(p.score), version: Number(p.version), defaulted: p.defaulted,
      onTime: Number(p.onTime), late: Number(p.late), streak: Number(p.streak),
      totalLimit: n(limit),
      base: { quota: n(qb), version: Number(vb), owed: n(ob) },
      unichain: { quota: n(qu), version: Number(vu), owed: n(ou) },
      reasons: explain({ set: r.set, helped: Number(r.helped), hurt: Number(r.hurt), helpedDelta: Number(r.helpedDelta), hurtDelta: Number(r.hurtDelta) }),
    };
  }

  async function recentScores(addr, blocks = 3000) {
    const head = await lasna.getBlockNumber();
    const logs = await reactive.queryFilter(reactive.filters.Scored(addr), Math.max(0, head - blocks), head);
    return logs.slice(-6).reverse().map((l) => ({ score: Number(l.args.score), tier: Number(l.args.tier), version: Number(l.args.version), tx: l.transactionHash, block: l.blockNumber }));
  }
  return { readWallet, recentScores };
}
