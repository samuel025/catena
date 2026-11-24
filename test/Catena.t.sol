// SPDX-License-Identifier: MIT
pragma solidity ^0.8.29;

import { Test } from "forge-std/Test.sol";
import { IPayable } from "@reactive/src/interfaces/IPayable.sol";
import { IReactive } from "@reactive/src/interfaces/IReactive.sol";
import { ISystemContract } from "@reactive/src/interfaces/ISystemContract.sol";
import { CatenaPool } from "../src/CatenaPool.sol";
import { CatenaReactive } from "../src/CatenaReactive.sol";

/// Stand-in for the Reactive system contract: records subscriptions and callback requests.
contract MockSystem {
    struct Req { uint256 chainId; address recipient; bytes payload; }
    Req[] public reqs;
    uint256 public subs;
    function subscribe(uint256, address, uint256, uint256, uint256, uint256) external { subs++; }
    function requestCallbackV_1_0(ISystemContract.CallbackConfiguration_V_1_0 memory c) external {
        reqs.push(Req(c.chainId, c.recipient, c.payload));
    }
    function debt(address) external pure returns (uint256) { return 0; }
    function n() external view returns (uint256) { return reqs.length; }
    function get(uint256 i) external view returns (Req memory) { return reqs[i]; }
}

contract CatenaTest is Test {
    address constant SYS = 0x8888888888888888888888888888888888888888;
    address payable proxy = payable(address(0xB0B));
    address ada = address(0xADA);
    uint256 constant BASE = 84532;
    uint256 constant UNI = 1301;

    CatenaReactive r;
    CatenaPool poolBase;
    CatenaPool poolUni;
    uint256 txn;

    function setUp() public {
        vm.etch(SYS, address(new MockSystem()).code);
        r = new CatenaReactive(60);
        poolBase = new CatenaPool(IPayable(proxy), address(r), false, 1 hours, 10 minutes);
        poolUni = new CatenaPool(IPayable(proxy), address(r), false, 1 hours, 10 minutes);
        uint256[] memory ids = new uint256[](2);
        ids[0] = BASE; ids[1] = UNI;
        address[] memory pools = new address[](2);
        pools[0] = address(poolBase); pools[1] = address(poolUni);
        r.setPools(ids, pools);
    }

    // ---- helpers ----
    function _log(uint256 chainId, address pool, uint256 topic0, bool late) internal returns (IReactive.LogRecord memory l) {
        l.chainId = chainId;
        l.contractAddress = pool;
        l.topic0 = topic0;
        l.topic1 = uint256(uint160(ada));
        l.data = abi.encode(uint256(10 ether), late);
        l.txHash = ++txn;
        l.logIndex = 0;
        l.opCode = 2;
    }
    function _repaid(uint256 chainId, address pool, bool late) internal returns (IReactive.LogRecord memory) {
        return _log(chainId, pool, uint256(keccak256("Repaid(address,uint256,bool)")), late);
    }
    function _react(IReactive.LogRecord memory l) internal { vm.prank(SYS); r.react(l); }
    function _reqs() internal view returns (uint256) { return MockSystem(SYS).n(); }

    function _decodeQuota(uint256 i) internal view returns (uint256 chainId, uint256 q, uint64 v) {
        MockSystem.Req memory q_ = MockSystem(SYS).get(i);
        bytes memory p = q_.payload;
        bytes memory args = new bytes(p.length - 4);
        for (uint256 k; k < args.length; ++k) args[k] = p[k + 4];
        (, , uint256 quota_, uint64 ver) = abi.decode(args, (address, address, uint256, uint64));
        return (q_.chainId, quota_, ver);
    }

    // ---- reactive ----
    function test_subscribesToThreeEventsPerPool() public view {
        assertEq(MockSystem(SYS).subs(), 6);
    }

    function test_onlySystemCanReact() public {
        IReactive.LogRecord memory l = _repaid(BASE, address(poolBase), false);
        vm.expectRevert();
        r.react(l);
    }

    function test_repayOnBaseRaisesQuotaOnBothChains() public {
        _react(_repaid(BASE, address(poolBase), false));
        assertEq(_reqs(), 2);
        (uint256 c0, uint256 q0,) = _decodeQuota(0);
        (uint256 c1, uint256 q1,) = _decodeQuota(1);
        assertEq(c0, BASE); assertEq(c1, UNI);
        assertEq(q0, 10 ether); assertEq(q1, 10 ether); // tier 1: 20 split over 2 chains
    }

    function test_duplicateEventIgnored() public {
        IReactive.LogRecord memory l = _repaid(BASE, address(poolBase), false);
        _react(l);
        _react(l);
        assertEq(_reqs(), 2);
    }

    function test_unknownPoolIgnored() public {
        _react(_repaid(BASE, address(0xBAD), false));
        assertEq(_reqs(), 0);
    }

    function test_slowClimbOneTierPerPeriod() public {
        _react(_repaid(BASE, address(poolBase), false));
        assertEq(r.tierOf(ada), 1);                       // first raise is immediate
        _react(_repaid(BASE, address(poolBase), false));
        assertEq(r.tierOf(ada), 1);                       // model says 2, but still inside the period
        vm.warp(block.timestamp + 61);
        _react(_repaid(BASE, address(poolBase), false));
        assertEq(r.tierOf(ada), 2);                       // next period: one more tier
        vm.warp(block.timestamp + 61);
        _react(_repaid(BASE, address(poolBase), false));
        assertLe(r.tierOf(ada), 3);
    }

    function test_cutIsImmediate() public {
        for (uint256 i; i < 3; ++i) { _react(_repaid(BASE, address(poolBase), false)); vm.warp(block.timestamp + 61); }
        uint8 before_ = r.tierOf(ada);
        for (uint256 i; i < 6; ++i) _react(_repaid(BASE, address(poolBase), true)); // six late payments, same instant
        assertLt(r.tierOf(ada), before_);
    }

    function test_defaultForcesZeroOnAllChains() public {
        for (uint256 i; i < 3; ++i) _react(_repaid(BASE, address(poolBase), false));
        uint256 before_ = _reqs();
        _react(_log(UNI, address(poolUni), uint256(keccak256("Defaulted(address)")), false));
        assertEq(_reqs(), before_ + 2);
        (, uint256 q0,) = _decodeQuota(before_);
        (, uint256 q1,) = _decodeQuota(before_ + 1);
        assertEq(q0, 0); assertEq(q1, 0);
    }

    // ---- pool ----
    function test_poolRejectsNonProxy() public {
        vm.expectRevert();
        poolBase.setQuota(address(r), ada, 10 ether, 1);
    }

    function test_poolRejectsWrongReactiveSender() public {
        vm.prank(proxy);
        vm.expectRevert();
        poolBase.setQuota(address(0xDEAD), ada, 10 ether, 1);
    }

    function test_poolIgnoresStaleVersion() public {
        vm.startPrank(proxy);
        poolBase.setQuota(address(r), ada, 20 ether, 2);
        poolBase.setQuota(address(r), ada, 0, 1); // stale
        vm.stopPrank();
        assertEq(poolBase.quota(ada), 20 ether);
    }

    function test_borrowRespectsQuotaAndCollateralOnlyRejects() public {
        CatenaPool co = new CatenaPool(IPayable(proxy), address(r), true, 1 hours, 10 minutes);
        vm.prank(proxy);
        poolUni.setQuota(address(r), ada, 10 ether, 1);
        vm.startPrank(ada);
        poolUni.borrow(10 ether);
        vm.expectRevert();
        poolUni.borrow(1);
        vm.expectRevert();
        co.borrow(1 ether); // collateral-only pool: Ada has none
        vm.stopPrank();
    }

    function test_lateRepayFlagAndDefaultMarking() public {
        vm.prank(proxy);
        poolBase.setQuota(address(r), ada, 10 ether, 1);
        vm.startPrank(ada);
        poolBase.borrow(5 ether);
        vm.warp(block.timestamp + 2 hours);
        vm.expectEmit(true, false, false, true);
        emit CatenaPool.Repaid(ada, 5 ether, true);
        poolBase.repay(5 ether);
        vm.stopPrank();
    }

    function test_unscoredWalletGetsStarterQuotaOnly() public {
        vm.startPrank(ada);
        poolBase.borrow(2 ether);
        vm.expectRevert();
        poolBase.borrow(1);
        vm.stopPrank();
        assertEq(poolBase.quotaOf(ada), 2 ether);
    }

    function test_defaultedWalletQuotaIsZeroNotStarter() public {
        _react(_log(UNI, address(poolUni), uint256(keccak256("Defaulted(address)")), false));
        vm.prank(proxy);
        poolUni.setQuota(address(r), ada, 0, 1);
        assertEq(poolUni.quotaOf(ada), 0);
    }

    /// A default is not instantaneous across chains. Locally it blocks borrowing at once; on the other chain the
    /// old quota stays live until the zero-quota callback lands (the window is the callback latency).
    function test_defaultBlocksLocallyAtOnceAndRemotelyAfterCallback() public {
        vm.startPrank(proxy);
        poolBase.setQuota(address(r), ada, 10 ether, 1);
        poolUni.setQuota(address(r), ada, 10 ether, 1);
        vm.stopPrank();
        vm.prank(ada);
        poolBase.borrow(2 ether);
        vm.warp(block.timestamp + 1 hours + 10 minutes + 1);
        poolBase.markDefault(ada);

        vm.prank(ada);
        vm.expectRevert();
        poolBase.borrow(1 ether); // local pool: blocked immediately, old quota notwithstanding

        vm.prank(ada);
        poolUni.borrow(3 ether); // remote pool: callback not delivered yet, so the old quota still works

        vm.prank(proxy);
        poolUni.setQuota(address(r), ada, 0, 2); // the zero-quota callback arrives
        vm.prank(ada);
        vm.expectRevert();
        poolUni.borrow(1 ether);

        vm.prank(proxy);
        poolUni.setQuota(address(r), ada, 10 ether, 1); // a stale callback cannot restore the old quota
        assertEq(poolUni.quotaOf(ada), 0);
    }

    function test_hybridCollateralAddsToHistoryQuota() public {
        vm.prank(proxy);
        poolBase.setQuota(address(r), ada, 10 ether, 1);
        vm.startPrank(ada);
        vm.deal(ada, 100 ether);
        vm.expectRevert();
        poolBase.borrow(14 ether); // above the 10 unsecured quota, no collateral yet
        poolBase.depositCollateral{ value: 8 ether }(); // secured part: 4
        assertEq(poolBase.borrowLimit(ada), 14 ether);
        poolBase.borrow(14 ether);
        vm.expectRevert();
        poolBase.borrow(1);
        vm.stopPrank();
    }

    function test_defaultRemovesUnsecuredPartButNotOwnCollateral() public {
        vm.prank(proxy);
        poolBase.setQuota(address(r), ada, 10 ether, 1);
        vm.deal(ada, 100 ether);
        vm.startPrank(ada);
        poolBase.depositCollateral{ value: 8 ether }();
        poolBase.borrow(1 ether);
        vm.warp(block.timestamp + 1 hours + 10 minutes + 1);
        vm.stopPrank();
        poolBase.markDefault(ada);
        assertEq(poolBase.borrowLimit(ada), 4 ether); // unsecured 10 gone at once, own collateral still counts
    }
}
