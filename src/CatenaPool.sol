// SPDX-License-Identifier: MIT
pragma solidity ^0.8.29;

import { IPayable } from "@reactive/src/interfaces/IPayable.sol";
import { AbstractCallback } from "@reactive/src/base/AbstractCallback.sol";

/// @title CatenaPool
/// @notice Demo lending pool (fake money, accounting only). Same code is deployed on every pool chain.
///         Borrow limits are per-borrower quotas set ONLY by the Catena reactive contract via callback.
///         In collateralOnly mode the pool ignores quotas, which the demo uses as the "before" case.
contract CatenaPool is AbstractCallback {
    // ---- origin events the reactive contract subscribes to ----
    event Borrowed(address indexed borrower, uint256 amount, uint256 dueAt);
    event Repaid(address indexed borrower, uint256 amount, bool late);
    event Defaulted(address indexed borrower);

    // ---- callback result ----
    event QuotaSet(address indexed borrower, uint256 quota, uint64 version);

    error QuotaExceeded(uint256 requested, uint256 available);
    error NothingOwed();
    error NotYetDefaulted();
    error NotCollateralOnly();

    /// @notice Seconds until a loan is due, and extra seconds before anyone may flag a default. Constructor
    ///         parameters so the demo can use minutes and a real deployment could use days.
    uint256 public immutable LOAN_PERIOD;
    uint256 public immutable GRACE;
    /// @notice Tier-0 starter limit for wallets with no score yet, so a thin file can take a first small loan.
    uint256 public constant STARTER_QUOTA = 2 ether;

    bool public immutable collateralOnly;

    mapping(address => uint256) public quota;
    mapping(address => uint64) public scoreVersion;
    mapping(address => uint256) public owed;
    mapping(address => uint256) public dueAt;
    mapping(address => uint256) public collateral;
    /// @notice Set locally the moment a default is flagged here. Blocks borrowing at once, without waiting for the
    ///         reactive contract's zero-quota callback (which matches the passport: a default is permanent).
    mapping(address => bool) public defaultFlagged;

    constructor(IPayable callbackProxy_, address reactive_, bool collateralOnly_, uint256 loanPeriod_, uint256 grace_)
        payable
        AbstractCallback(callbackProxy_, reactive_)
    {
        collateralOnly = collateralOnly_;
        LOAN_PERIOD = loanPeriod_;
        GRACE = grace_;
    }

    // ---- callback (only the proxy, only our reactive contract) ----

    /// @param reactive_ injected by the proxy (first 160 bits of payload); pass address(0) when encoding.
    function setQuota(address reactive_, address borrower, uint256 newQuota, uint64 version)
        external
        onlyServiceProvider
        onlyCallbackSender(reactive_)
    {
        if (version <= scoreVersion[borrower]) return; // stale or replayed update: ignore, do not revert
        scoreVersion[borrower] = version;
        quota[borrower] = newQuota;
        emit QuotaSet(borrower, newQuota, version);
    }

    /// @notice Public debt settlement so anyone can revive a pool stalled in callback debt.
    function coverDebt() external {
        _coverDebt();
    }

    /// @notice Effective per-chain limit: starter until the first score arrives, then the pushed quota.
    function quotaOf(address borrower) public view returns (uint256) {
        return scoreVersion[borrower] == 0 ? STARTER_QUOTA : quota[borrower];
    }

    // ---- demo user actions ----

    function depositCollateral() external payable {
        collateral[msg.sender] += msg.value;
    }

    /// @notice Hybrid limit. Unsecured part = the history-based quota (zero once a default is flagged here, even
    ///         before the zero-quota callback arrives). Secured part = half of the posted collateral, always
    ///         available. In collateralOnly mode (the "before" case) only the secured part counts.
    ///         Collateral is accounting only in this demo: there is no withdrawal and no liquidation.
    function borrowLimit(address borrower) public view returns (uint256) {
        uint256 secured = collateral[borrower] / 2;
        if (collateralOnly) return secured;
        return (defaultFlagged[borrower] ? 0 : quotaOf(borrower)) + secured;
    }

    function borrow(uint256 amount) external {
        uint256 limit = borrowLimit(msg.sender);
        uint256 newOwed = owed[msg.sender] + amount;
        if (newOwed > limit) revert QuotaExceeded(amount, limit > owed[msg.sender] ? limit - owed[msg.sender] : 0);
        owed[msg.sender] = newOwed;
        uint256 due = block.timestamp + LOAN_PERIOD; // timestamps, not blocks (Base Sepolia is 200ms)
        dueAt[msg.sender] = due;
        emit Borrowed(msg.sender, amount, due);
    }

    function repay(uint256 amount) external {
        uint256 o = owed[msg.sender];
        if (o == 0) revert NothingOwed();
        if (amount > o) amount = o;
        owed[msg.sender] = o - amount;
        emit Repaid(msg.sender, amount, block.timestamp > dueAt[msg.sender]);
    }

    /// @notice Anyone can flag a borrower who is past due + grace.
    function markDefault(address borrower) external {
        if (owed[borrower] == 0 || block.timestamp <= dueAt[borrower] + GRACE) revert NotYetDefaulted();
        defaultFlagged[borrower] = true;
        emit Defaulted(borrower);
    }
}
