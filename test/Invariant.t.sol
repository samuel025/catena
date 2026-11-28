// SPDX-License-Identifier: MIT
pragma solidity ^0.8.29;

import { Test } from "forge-std/Test.sol";
import { Vm } from "forge-std/Vm.sol";
import { IPayable } from "@reactive/src/interfaces/IPayable.sol";
import { IReactive } from "@reactive/src/interfaces/IReactive.sol";
import { CatenaPool } from "../src/CatenaPool.sol";
import { CatenaReactive } from "../src/CatenaReactive.sol";
import { MockSystem } from "./Catena.t.sol";

/// Drives the whole system the way the network would, but in an adversarial order: three wallets borrow, repay, post
/// collateral and get flagged for default on two pools; pool events reach the reactive contract one at a time; callbacks
/// are delivered in any order, late, more than once, or never. Every property is checked as it happens and counted in
/// `violations`, so a broken rule fails the run even though handler calls themselves never revert the test.
contract CatenaHandler is Test {
    address constant SYS = 0x8888888888888888888888888888888888888888;
    uint256 constant RAISE_PERIOD = 60;
    bytes32 constant BORROWED = keccak256("Borrowed(address,uint256,uint256)");
    bytes32 constant REPAID = keccak256("Repaid(address,uint256,bool)");
    bytes32 constant DEFAULTED = keccak256("Defaulted(address)");

    CatenaReactive public r;
    CatenaPool[2] public pools;
    uint256[2] public chainIds = [uint256(84532), 1301];
    address payable public proxy;
    address[3] public actors = [address(0xA11CE), address(0xB0B0), address(0xCA401)];

    IReactive.LogRecord[] internal queue; // pool events not yet seen by the reactive contract
    uint256 internal next;                // next queue index to relay (events reach Lasna in order)
    uint256 internal txn;

    // ---- ghost state ----
    uint256 public violations;
    string public lastViolation;
    mapping(address => bool) public everDefaulted;
    mapping(address => bool) internal borrowedSinceRescore;
    mapping(address => bool) internal lastRescoreCut; // the last rescore lowered the tier (shrinks the debt-ratio scale)
    mapping(uint256 => mapping(address => uint64)) public maxDelivered;   // pool index => actor => version
    mapping(uint256 => mapping(address => uint256)) public quotaAtMax;    // quota carried by that version
    uint256 public calls_borrow; uint256 public calls_relay; uint256 public calls_deliver; uint256 public calls_default;

    constructor(CatenaReactive r_, CatenaPool a, CatenaPool b, address payable proxy_) {
        r = r_; pools[0] = a; pools[1] = b; proxy = proxy_;
    }

    function _fail(string memory why) internal { violations++; lastViolation = why; }

    function _actor(uint256 s) internal view returns (address) { return actors[s % 3]; }

    /// The limit the pool must enforce, written out independently of CatenaPool.borrowLimit.
    function _expectedLimit(CatenaPool p, address a) internal view returns (uint256) {
        bool flagged = p.defaultFlagged(a);
        if (flagged && p.owed(a) > 0) return 0;
        uint256 unsecured = flagged ? 0 : (p.scoreVersion(a) == 0 ? p.STARTER_QUOTA() : p.quota(a));
        return unsecured + p.collateral(a) / 2;
    }

    function _capture(uint256 pi) internal {
        Vm.Log[] memory logs = vm.getRecordedLogs();
        for (uint256 i; i < logs.length; ++i) {
            if (logs[i].emitter != address(pools[pi])) continue;
            bytes32 t0 = logs[i].topics[0];
            if (t0 != BORROWED && t0 != REPAID && t0 != DEFAULTED) continue;
            IReactive.LogRecord memory l;
            l.chainId = chainIds[pi];
            l.contractAddress = address(pools[pi]);
            l.topic0 = uint256(t0);
            l.topic1 = uint256(logs[i].topics[1]);
            l.data = logs[i].data;
            l.txHash = ++txn;
            l.opCode = 2;
            queue.push(l);
        }
    }

    // ---- actions ----

    function borrow(uint256 actorSeed, uint256 poolSeed, uint256 amount) external {
        address a = _actor(actorSeed);
        uint256 pi = poolSeed % 2;
        CatenaPool p = pools[pi];
        amount = bound(amount, 1, 60 ether);
        uint256 limit = _expectedLimit(p, a);
        bool shouldPass = p.owed(a) + amount <= limit;
        vm.recordLogs();
        vm.prank(a);
        try p.borrow(amount) {
            calls_borrow++;
            if (!shouldPass) _fail("borrow above the limit succeeded");
            if (p.owed(a) > limit) _fail("owed exceeds the limit after a borrow");
        } catch {
            if (shouldPass) _fail("borrow within the limit reverted");
        }
        _capture(pi);
    }

    function repay(uint256 actorSeed, uint256 poolSeed, uint256 amount) external {
        address a = _actor(actorSeed);
        uint256 pi = poolSeed % 2;
        CatenaPool p = pools[pi];
        if (p.owed(a) == 0) return;
        amount = amount % 2 == 0 ? p.owed(a) : bound(amount, 1, p.owed(a)); // half the time, repay in full
        vm.recordLogs();
        vm.prank(a);
        p.repay(amount);
        _capture(pi);
    }

    function depositCollateral(uint256 actorSeed, uint256 poolSeed, uint256 amount) external {
        address a = _actor(actorSeed);
        amount = bound(amount, 1, 20 ether);
        vm.deal(a, amount);
        vm.prank(a);
        pools[poolSeed % 2].depositCollateral{ value: amount }();
    }

    function markDefault(uint256 actorSeed, uint256 poolSeed) external {
        address a = _actor(actorSeed);
        uint256 pi = poolSeed % 2;
        CatenaPool p = pools[pi];
        if (p.owed(a) == 0) return;
        if (block.timestamp <= p.dueAt(a) + p.GRACE()) vm.warp(p.dueAt(a) + p.GRACE() + 1);
        vm.recordLogs();
        p.markDefault(a);
        calls_default++;
        if (p.borrowLimit(a) != 0) _fail("flagged borrower who still owes has a nonzero limit");
        _capture(pi);
    }

    function warp(uint256 secs) external {
        vm.warp(block.timestamp + bound(secs, 1, 2 hours));
    }

    /// Deliver the next pool event to the reactive contract and check the scoring rules on the result.
    function relay() external {
        if (next >= queue.length) return;
        IReactive.LogRecord memory l = queue[next++];
        address a = address(uint160(l.topic1));
        (, , , , , bool def0, uint8 tier0, uint16 score0, , , uint64 raise0, ) = r.passports(a);
        uint256 reqs0 = MockSystem(SYS).n();

        vm.prank(SYS);
        r.react(l);
        calls_relay++;

        (, , , , , bool def1, uint8 tier1, uint16 score1, uint64 ver1, , , ) = r.passports(a);
        if (everDefaulted[a] && !def1) _fail("a default was forgotten");
        if (def1) everDefaulted[a] = true;
        if (def1 && tier1 != 0) _fail("defaulted borrower has a nonzero tier");
        if (tier1 > tier0) {
            if (tier1 != tier0 + 1) _fail("tier rose by more than one step");
            if (raise0 != 0 && block.timestamp < uint256(raise0) + RAISE_PERIOD) _fail("tier rose inside the raise period");
        }
        if (bytes32(l.topic0) == REPAID) {
            (, bool late) = abi.decode(l.data, (uint256, bool));
            if (!late && !def0 && !borrowedSinceRescore[a]) {
                if (tier1 < tier0) _fail("an on-time repayment with no new borrowing lowered the tier");
                // Every input moves the favourable way, so the monotone model's score cannot fall. Skipped after a cut,
                // which shrinks the limit the debt ratio is measured against.
                if (ver1 > 1 && !lastRescoreCut[a] && score1 < score0) _fail("an on-time repayment lowered the score");
            }
        }
        if (bytes32(l.topic0) == BORROWED) {
            borrowedSinceRescore[a] = true;
        } else {
            borrowedSinceRescore[a] = false;
            lastRescoreCut[a] = tier1 < tier0;
        }

        // Every callback requested now carries quota zero for a defaulted borrower.
        uint256 reqs1 = MockSystem(SYS).n();
        for (uint256 i = reqs0; i < reqs1; ++i) {
            (, address who, uint256 q, ) = _decode(i);
            if (who == a && def1 && q != 0) _fail("callback for a defaulted borrower carries a nonzero quota");
        }
    }

    /// Send an event the reactive contract has already processed once more: it must change nothing.
    function replay(uint256 seed) external {
        if (next == 0) return;
        IReactive.LogRecord memory l = queue[seed % next];
        address a = address(uint160(l.topic1));
        bytes32 before = _passportHash(a);
        uint256 reqs0 = MockSystem(SYS).n();
        vm.prank(SYS);
        r.react(l);
        if (_passportHash(a) != before) _fail("a duplicate event changed the passport");
        if (MockSystem(SYS).n() != reqs0) _fail("a duplicate event requested callbacks");
    }

    /// Deliver any requested callback, in any order and possibly again: the pool must keep the newest version.
    function deliver(uint256 seed) external {
        uint256 n = MockSystem(SYS).n();
        if (n == 0) return;
        uint256 i = seed % n;
        (uint256 pi, address who, uint256 q, uint64 v) = _decode(i);
        vm.prank(proxy);
        pools[pi].setQuota(address(r), who, q, v);
        calls_deliver++;
        if (v > maxDelivered[pi][who]) { maxDelivered[pi][who] = v; quotaAtMax[pi][who] = q; }
    }

    function _passportHash(address a) internal view returns (bytes32) {
        (, bytes memory raw) = address(r).staticcall(abi.encodeCall(r.passports, (a)));
        return keccak256(raw);
    }

    function _decode(uint256 i) internal view returns (uint256 pi, address who, uint256 q, uint64 v) {
        MockSystem.Req memory req = MockSystem(SYS).get(i);
        bytes memory p = req.payload;
        bytes memory args = new bytes(p.length - 4);
        for (uint256 k; k < args.length; ++k) args[k] = p[k + 4];
        (, who, q, v) = abi.decode(args, (address, address, uint256, uint64));
        pi = req.recipient == address(pools[0]) ? 0 : 1;
    }
}

/// forge-config: default.invariant.runs = 64
/// forge-config: default.invariant.depth = 80
contract CatenaInvariantTest is Test {
    address constant SYS = 0x8888888888888888888888888888888888888888;
    CatenaHandler h;
    CatenaReactive r;
    CatenaPool[2] pools;

    function setUp() public {
        vm.etch(SYS, address(new MockSystem()).code);
        address payable proxy = payable(address(0xB0B));
        r = new CatenaReactive(60);
        pools[0] = new CatenaPool(IPayable(proxy), address(r), false, 1 hours, 10 minutes);
        pools[1] = new CatenaPool(IPayable(proxy), address(r), false, 1 hours, 10 minutes);
        uint256[] memory ids = new uint256[](2);
        ids[0] = 84532; ids[1] = 1301;
        address[] memory ps = new address[](2);
        ps[0] = address(pools[0]); ps[1] = address(pools[1]);
        r.setPools(ids, ps);
        h = new CatenaHandler(r, pools[0], pools[1], proxy);

        bytes4[] memory sel = new bytes4[](8);
        sel[0] = h.borrow.selector; sel[1] = h.repay.selector; sel[2] = h.depositCollateral.selector;
        sel[3] = h.markDefault.selector; sel[4] = h.warp.selector; sel[5] = h.relay.selector; sel[6] = h.deliver.selector; sel[7] = h.replay.selector;
        targetSelector(FuzzSelector({ addr: address(h), selectors: sel }));
        targetContract(address(h));
    }

    /// Every rule checked during the run held (borrow limit, default permanence, slow climb, on-time monotonicity,
    /// zero quota for defaulters).
    function invariant_noRuleBroken() public view {
        assertEq(h.violations(), 0, h.lastViolation());
    }

    /// Each pool holds exactly the quota from the newest callback it received, whatever the delivery order.
    function invariant_poolKeepsNewestVersion() public view {
        for (uint256 pi; pi < 2; ++pi) {
            for (uint256 k; k < 3; ++k) {
                address a = h.actors(k);
                assertEq(pools[pi].scoreVersion(a), h.maxDelivered(pi, a), "pool version is not the newest delivered");
                if (h.maxDelivered(pi, a) > 0) assertEq(pools[pi].quota(a), h.quotaAtMax(pi, a), "pool quota is not from the newest version");
            }
        }
    }

    /// A borrower flagged for default on a pool, who still owes there, can borrow nothing on that pool.
    function invariant_flaggedDebtorBlocked() public view {
        for (uint256 pi; pi < 2; ++pi) {
            for (uint256 k; k < 3; ++k) {
                address a = h.actors(k);
                if (pools[pi].defaultFlagged(a) && pools[pi].owed(a) > 0) assertEq(pools[pi].borrowLimit(a), 0);
            }
        }
    }

    /// A borrower flagged for default on a pool gets no unsecured credit there, even after repaying: only collateral counts.
    function invariant_flaggedHasNoUnsecuredCredit() public view {
        for (uint256 pi; pi < 2; ++pi) {
            for (uint256 k; k < 3; ++k) {
                address a = h.actors(k);
                if (pools[pi].defaultFlagged(a)) assertLe(pools[pi].borrowLimit(a), pools[pi].collateral(a) / 2);
            }
        }
    }

    /// Once a pool has the newest version for a defaulted borrower, its unsecured quota is zero.
    function invariant_defaulterHasZeroQuotaOnceSynced() public view {
        for (uint256 k; k < 3; ++k) {
            address a = h.actors(k);
            (, , , , , bool def, , , uint64 ver, , , ) = r.passports(a);
            if (!def) continue;
            for (uint256 pi; pi < 2; ++pi) {
                if (pools[pi].scoreVersion(a) == ver) assertEq(pools[pi].quotaOf(a), 0, "synced pool gives a defaulter credit");
            }
        }
    }
}
