// SPDX-License-Identifier: MIT
pragma solidity ^0.8.29;

import { ISystemContract } from "@reactive/src/interfaces/ISystemContract.sol";
import { IReactive } from "@reactive/src/interfaces/IReactive.sol";
import { AbstractReactive } from "@reactive/src/base/AbstractReactive.sol";
import { Mlp } from "./Mlp.sol";

/// @title CatenaReactive
/// @notice Watches loan events on every pool chain, keeps one passport per borrower, scores it,
///         and sets per-chain quotas by callback. The tier comes from the fixed-point MLP in `Mlp.sol`;
///         a default and the slow-climb period are hard rules outside the model.
contract CatenaReactive is AbstractReactive {
    error NotOwner();
    error PoolsAlreadySet();

    uint64 internal constant CALLBACK_GAS = 300_000;
    uint256 internal constant HISTORY_WINDOW = 1 days;
    int256 internal constant S = 1024;

    uint256 internal constant BORROWED_TOPIC0 = uint256(keccak256("Borrowed(address,uint256,uint256)"));
    uint256 internal constant REPAID_TOPIC0 = uint256(keccak256("Repaid(address,uint256,bool)"));
    uint256 internal constant DEFAULTED_TOPIC0 = uint256(keccak256("Defaulted(address)"));

    struct Passport {
        uint32 onTime;
        uint32 late;
        uint32 streak;      // on-time repayments since the last late one
        uint8 recentLate;   // bit i = repayment i ago was late (last 5)
        uint8 recentCount;  // repayments seen, capped at 5
        bool defaulted;
        uint8 tier;
        uint16 score;       // last model score, 0..1024
        uint64 version;
        uint64 firstSeen;
        uint64 lastRaiseAt;
        uint256 debt;       // outstanding, from Borrowed and Repaid amounts
    }

    event Scored(address indexed borrower, uint16 score, uint8 tier, uint64 version);

    /// @notice Why the tier changed. Feature ids: 0 on_time, 1 late_ratio, 2 consistency, 3 debt_ratio,
    ///         4 history, 5 recency, NO_REASON none, REASON_DEFAULT the hard default rule.
    ///         Deltas are model sensitivity (score minus score with that input set to a typical borrower), not
    ///         the definitive cause.
    event Reasons(address indexed borrower, uint8 helped, int16 helpedDelta, uint8 hurt, int16 hurtDelta);

    uint8 internal constant NO_REASON = 6;
    uint8 internal constant REASON_DEFAULT = 7;

    struct Reason {
        uint8 helped;
        uint8 hurt;
        int16 helpedDelta;
        int16 hurtDelta;
        bool set; // false until the first tier change
    }
    mapping(address => Reason) public reasons;

    address public immutable owner;
    /// @notice Minimum seconds between tier raises for one borrower (cuts are immediate).
    uint256 public immutable raisePeriod;
    uint256[] public poolChains;
    mapping(uint256 => address) public poolOf; // chainId => pool
    bool public poolsSet;

    mapping(address => Passport) public passports;
    mapping(bytes32 => bool) public seen; // dedup: chainId, txHash, logIndex

    /// @notice Total credit limit per tier, split evenly into per-chain quotas. Tier 0 matches the pool's starter quota.
    uint256[4] public tierLimit = [uint256(4 ether), 20 ether, 50 ether, 100 ether];

    constructor(uint256 raisePeriod_) payable {
        owner = msg.sender;
        raisePeriod = raisePeriod_;
    }

    function tierOf(address borrower) external view returns (uint8) {
        return passports[borrower].tier;
    }

    /// @notice Set pools once (after they are deployed with this contract as callback sender) and subscribe.
    function setPools(uint256[] calldata chainIds, address[] calldata pools) external {
        if (msg.sender != owner) revert NotOwner();
        if (poolsSet) revert PoolsAlreadySet();
        poolsSet = true;
        for (uint256 i; i < chainIds.length; ++i) {
            poolChains.push(chainIds[i]);
            poolOf[chainIds[i]] = pools[i];
            SYSTEM.subscribe(chainIds[i], pools[i], BORROWED_TOPIC0, REACTIVE_IGNORE, REACTIVE_IGNORE, REACTIVE_IGNORE);
            SYSTEM.subscribe(chainIds[i], pools[i], REPAID_TOPIC0, REACTIVE_IGNORE, REACTIVE_IGNORE, REACTIVE_IGNORE);
            SYSTEM.subscribe(chainIds[i], pools[i], DEFAULTED_TOPIC0, REACTIVE_IGNORE, REACTIVE_IGNORE, REACTIVE_IGNORE);
        }
    }

    /// @notice Anyone can settle debt so a stalled contract can be revived.
    function coverDebt() external {
        _coverDebt();
    }

    /// @inheritdoc IReactive
    function react(LogRecord memory log_) external onlySystem {
        // Only act on events from the registered pool on that chain. Never revert as a filter.
        if (poolOf[log_.chainId] != log_.contractAddress || log_.contractAddress == address(0)) return;
        bytes32 key = keccak256(abi.encode(log_.chainId, log_.txHash, log_.logIndex));
        if (seen[key]) return;
        seen[key] = true;

        address borrower = address(uint160(log_.topic1));
        Passport storage p = passports[borrower];
        if (p.firstSeen == 0) p.firstSeen = uint64(block.timestamp);

        if (log_.topic0 == BORROWED_TOPIC0) {
            (uint256 amount,) = abi.decode(log_.data, (uint256, uint256));
            p.debt += amount;
            return; // debt is tracked; scoring happens on repay or default
        } else if (log_.topic0 == REPAID_TOPIC0) {
            (uint256 amount, bool late) = abi.decode(log_.data, (uint256, bool));
            p.debt = amount >= p.debt ? 0 : p.debt - amount;
            _recordRepayment(p, late);
        } else if (log_.topic0 == DEFAULTED_TOPIC0) {
            p.defaulted = true;
        } else {
            return;
        }

        _rescore(borrower, p);
    }

    /// @dev Score, apply the hard rules, explain only if the tier moved, then push quotas to every pool.
    function _rescore(address borrower, Passport storage p) internal {
        int256[6] memory x = _features(p);
        uint256 s = Mlp.score(x);
        uint8 newTier = _applyRules(p, Mlp.tier(s));
        bool tierChanged = newTier != p.tier;
        p.score = uint16(s);
        p.tier = newTier;
        p.version += 1;
        emit Scored(borrower, uint16(s), newTier, p.version);
        if (tierChanged) _explain(borrower, p, x, s); // six extra passes, only when the tier moves
        _pushQuotas(borrower, p);
    }

    function _recordRepayment(Passport storage p, bool late) internal {
        p.recentLate = uint8(((uint256(p.recentLate) << 1) | (late ? 1 : 0)) & 0x1F);
        if (p.recentCount < 5) p.recentCount += 1;
        if (late) {
            p.late += 1;
            p.streak = 0;
        } else {
            p.onTime += 1;
            p.streak += 1;
        }
    }

    /// @dev Hard rules around the model: a default is zero, cuts are immediate, raises climb one tier per period.
    function _applyRules(Passport storage p, uint8 modelTier) internal returns (uint8) {
        if (p.defaulted) return 0;
        if (modelTier <= p.tier) return modelTier;
        if (p.lastRaiseAt == 0 || block.timestamp >= uint256(p.lastRaiseAt) + raisePeriod) {
            p.lastRaiseAt = uint64(block.timestamp);
            return p.tier + 1;
        }
        return p.tier;
    }

    /// @dev Builds the six model inputs (all in [0, 1024]) exactly as model/train.py defines them.
    function _features(Passport storage p) internal view returns (int256[6] memory x) {
        uint256 on = p.onTime;
        uint256 tot = on + p.late;
        uint256 limit = tierLimit[p.tier];
        uint256 onTimeRecent = p.recentCount - _popcount(p.recentLate);
        uint256 age = block.timestamp - p.firstSeen;
        uint256 streak = p.streak;
        x[0] = int256((on > 10 ? 10 : on) * 1024 / 10);
        x[1] = tot == 0 ? int256(0) : int256(uint256(p.late) * 1024 / tot);
        x[2] = int256(onTimeRecent * 1024 / 5);
        x[3] = int256((p.debt > limit ? limit : p.debt) * 1024 / limit);
        x[4] = int256((age > HISTORY_WINDOW ? HISTORY_WINDOW : age) * 1024 / HISTORY_WINDOW);
        x[5] = int256((streak > 10 ? 10 : streak) * 1024 / 10);
    }

    function _explain(address borrower, Passport storage p, int256[6] memory x, uint256 s) internal {
        Reason memory r = Reason(NO_REASON, NO_REASON, 0, 0, true);
        if (p.defaulted) r.hurt = REASON_DEFAULT; // a hard rule, not a model sensitivity
        else _sensitivities(r, x, s);
        Reason storage rs = reasons[borrower];
        rs.helped = r.helped; rs.hurt = r.hurt; rs.helpedDelta = r.helpedDelta; rs.hurtDelta = r.hurtDelta; rs.set = true;
        emit Reasons(borrower, r.helped, r.helpedDelta, r.hurt, r.hurtDelta);
    }

    /// @dev Swap each input for its typical-borrower value and keep the largest rise and largest drop.
    function _sensitivities(Reason memory r, int256[6] memory x, uint256 s) internal pure {
        int256[6] memory b = Mlp.baseline();
        for (uint8 i; i < 6; ++i) {
            int256 d = int256(s) - int256(_scoreSwapped(x, i, b[i]));
            if (d > r.helpedDelta) { r.helpedDelta = int16(d); r.helped = i; }
            if (d < r.hurtDelta) { r.hurtDelta = int16(d); r.hurt = i; }
        }
    }

    function _scoreSwapped(int256[6] memory x, uint8 i, int256 v) internal pure returns (uint256 sc) {
        int256 old = x[i];
        x[i] = v;
        sc = Mlp.score(x);
        x[i] = old;
    }

    function _popcount(uint8 v) internal pure returns (uint256 c) {
        while (v != 0) { c += v & 1; v >>= 1; }
    }

    function _pushQuotas(address borrower, Passport storage p) internal {
        uint256 n = poolChains.length;
        uint256 quotaEach = p.defaulted ? 0 : tierLimit[p.tier] / n;
        for (uint256 i; i < n; ++i) {
            uint256 chainId = poolChains[i];
            bytes memory payload = abi.encodeWithSignature(
                "setQuota(address,address,uint256,uint64)",
                address(0), // replaced by the proxy with this contract's address
                borrower,
                quotaEach,
                p.version
            );
            SYSTEM.requestCallbackV_1_0(
                ISystemContract.CallbackConfiguration_V_1_0({
                    chainId: chainId,
                    recipient: poolOf[chainId],
                    gasLimit: CALLBACK_GAS,
                    payload: payload
                })
            );
        }
    }
}
