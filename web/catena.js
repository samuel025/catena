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
  "function collateral(address) view returns (uint256)",
  "function borrowLimit(address) view returns (uint256)",
  "function defaultFlagged(address) view returns (bool)",
];

export const S = 1024;
export const WINDOW = 86400; // CatenaReactive.HISTORY_WINDOW
export const BASELINE = [512, 205, 614, 307, 512, 512]; // typical borrower, model/train.py
export const FEATURE_NAMES = ["On-time repayments", "Late-payment ratio", "Recent consistency", "Debt against limit", "History length", "On-time streak"];
export const FEATURE_SIGN = [1, -1, 1, -1, 1, 1]; // +1: higher is better for the score

const popcount = (v) => v.toString(2).split("1").length - 1;

/** The six model inputs (0..1024), mirroring CatenaReactive._features. History length uses `now` (seconds). */
export function features(p, limit, now) {
  const tot = p.onTime + p.late;
  const onRecent = p.recentCount - popcount(p.recentLate);
  const age = p.firstSeen > 0 ? Math.max(0, now - p.firstSeen) : 0;
  const debt = p.debt < limit ? p.debt : limit;
  return [
    Math.floor((Math.min(p.onTime, 10) * S) / 10),
    tot ? Math.floor((p.late * S) / tot) : 0,
    Math.floor((onRecent * S) / 5),
    limit > 0n ? Number((debt * BigInt(S)) / limit) : 0,
    Math.floor((Math.min(age, WINDOW) * S) / WINDOW),
    Math.floor((Math.min(p.streak, 10) * S) / 10),
  ];
}

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

  let limitsP = null; // tier limits never change after deployment, so read them once
  const tierLimits = () => (limitsP ||= Promise.all([0, 1, 2, 3].map((t) => reactive.tierLimit(t))).then((a) => a.map((x) => Number(x / 10n ** 16n) / 100)));

  async function readWallet(addr) {
    const [p, r, qb, qu, vb, vu, ob, ou, cb, cu, lb, lu, fb, fu] = await Promise.all([
      reactive.passports(addr), reactive.reasons(addr),
      poolBase.quotaOf(addr), poolUni.quotaOf(addr),
      poolBase.scoreVersion(addr), poolUni.scoreVersion(addr),
      poolBase.owed(addr), poolUni.owed(addr),
      poolBase.collateral(addr), poolUni.collateral(addr),
      poolBase.borrowLimit(addr), poolUni.borrowLimit(addr),
      poolBase.defaultFlagged(addr), poolUni.defaultFlagged(addr),
    ]);
    const limit = await reactive.tierLimit(p.tier);
    const unit = 10n ** 18n;
    const n = (x) => Number(x / (unit / 100n)) / 100; // whole units with 2 decimals
    const n6 = (x) => Number(x / (unit / 1000000n)) / 1000000; // collateral is real testnet ETH, so keep 6 decimals
    return {
      tier: Number(p.tier), score: Number(p.score), version: Number(p.version), defaulted: p.defaulted,
      onTime: Number(p.onTime), late: Number(p.late), streak: Number(p.streak),
      totalLimit: n(limit),
      limits: await tierLimits(),
      firstSeen: Number(p.firstSeen),
      inputs: features({ onTime: Number(p.onTime), late: Number(p.late), streak: Number(p.streak), recentLate: Number(p.recentLate), recentCount: Number(p.recentCount), firstSeen: Number(p.firstSeen), debt: p.debt }, limit, Math.floor(Date.now() / 1000)),
      base: { quota: n(qb), version: Number(vb), owed: n(ob), secured: n6(cb / 2n), collateral: n6(cb), limit: n6(lb), flagged: fb },
      unichain: { quota: n(qu), version: Number(vu), owed: n(ou), secured: n6(cu / 2n), collateral: n6(cu), limit: n6(lu), flagged: fu },
      reasons: explain({ set: r.set, helped: Number(r.helped), hurt: Number(r.hurt), helpedDelta: Number(r.helpedDelta), hurtDelta: Number(r.hurtDelta) }),
    };
  }

  async function recentScores(addr, blocks = 3000) {
    const head = await lasna.getBlockNumber();
    const logs = await reactive.queryFilter(reactive.filters.Scored(addr), Math.max(0, head - blocks), head);
    return logs.slice(-6).reverse().map((l) => ({ score: Number(l.args.score), tier: Number(l.args.tier), version: Number(l.args.version), tx: l.transactionHash, block: l.blockNumber }));
  }
  async function heads() {
    const one = async (p) => { const t = performance.now(); const b = await p.getBlockNumber(); return { block: b, ms: Math.round(performance.now() - t) }; };
    const [l, b, u] = await Promise.allSettled([one(lasna), one(base), one(uni)]);
    const v = (x) => (x.status === "fulfilled" ? x.value : null);
    return { lasna: v(l), base: v(b), unichain: v(u) };
  }
  return { readWallet, recentScores, heads };
}
