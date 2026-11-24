// SPDX-License-Identifier: MIT
pragma solidity ^0.8.29;

import { Test } from "forge-std/Test.sol";
import { IPayable } from "@reactive/src/interfaces/IPayable.sol";
import { AbstractPayer } from "@reactive/src/base/AbstractPayer.sol";
import { CatenaPool } from "../src/CatenaPool.sol";
import { CatenaReactive } from "../src/CatenaReactive.sol";

/// Stand-in for a callback proxy / system contract that bills for callbacks: a settable debt and a payable fallback.
contract MockBiller {
    mapping(address => uint256) public debt;
    uint256 public received;
    function setDebt(address who, uint256 d) external { debt[who] = d; }
    receive() external payable { received += msg.value; }
}

/// What happens when a contract cannot pay for its callbacks. The network itself stops delivering to a contract in
/// debt (observed on testnet); these tests pin down the contract-side behaviour we control.
contract FundsTest is Test {
    address constant SYS = 0x8888888888888888888888888888888888888888;
    address payable proxy = payable(address(0xB0B));
    address ada = address(0xADA);
    CatenaReactive r;
    CatenaPool pool;

    function setUp() public {
        vm.etch(proxy, address(new MockBiller()).code);
        vm.etch(SYS, address(new MockBiller()).code);
        r = new CatenaReactive(60);
        pool = new CatenaPool(IPayable(proxy), address(r), false, 1 hours, 10 minutes);
    }

    function test_poolCannotCoverDebtWithoutFundsAndNothingElseBreaks() public {
        MockBiller(proxy).setDebt(address(pool), 0.5 ether);
        vm.expectRevert(abi.encodeWithSelector(AbstractPayer.InsufficientFunds.selector, 0.5 ether, 0));
        pool.coverDebt();
        // an unfunded pool still enforces what it has: starter quota works, limits hold
        vm.startPrank(ada);
        pool.borrow(2 ether);
        vm.expectRevert();
        pool.borrow(1);
        vm.stopPrank();
    }

    function test_anyoneCanReviveAPoolByFundingIt() public {
        MockBiller(proxy).setDebt(address(pool), 0.5 ether);
        vm.deal(address(this), 1 ether);
        (bool ok,) = address(pool).call{ value: 0.6 ether }("");
        assertTrue(ok);
        pool.coverDebt();
        assertEq(MockBiller(proxy).received(), 0.5 ether);
        assertEq(address(pool).balance, 0.1 ether);
    }

    function test_proxyPullIsRefusedWhenBalanceTooLow() public {
        vm.deal(address(pool), 0.1 ether);
        vm.prank(proxy);
        vm.expectRevert(abi.encodeWithSelector(AbstractPayer.InsufficientFunds.selector, 0.3 ether, 0.1 ether));
        pool.pay(0.3 ether);
        vm.prank(address(0xBAD));
        vm.expectRevert(); // only the proxy may pull funds
        pool.pay(0.01 ether);
    }

    /// An exhausted pool is the dangerous case for cuts: the zero-quota callback may never arrive. The local
    /// default flag does not depend on funds or callbacks, so the pool still shuts off unsecured credit.
    function test_localDefaultFlagWorksWithAnEmptyPool() public {
        vm.prank(proxy);
        pool.setQuota(address(r), ada, 10 ether, 1);
        vm.prank(ada);
        pool.borrow(2 ether);
        assertEq(address(pool).balance, 0);
        vm.warp(block.timestamp + 1 hours + 10 minutes + 1);
        pool.markDefault(ada);
        assertEq(pool.borrowLimit(ada), 0);
        vm.prank(ada);
        vm.expectRevert();
        pool.borrow(1);
    }

    function test_reactiveContractDebtNeedsFundsThenClears() public {
        MockBiller(payable(SYS)).setDebt(address(r), 0.2 ether);
        vm.expectRevert(abi.encodeWithSelector(AbstractPayer.InsufficientFunds.selector, 0.2 ether, 0));
        r.coverDebt();
        vm.deal(address(r), 0.25 ether);
        r.coverDebt();
        assertEq(MockBiller(payable(SYS)).received(), 0.2 ether);
    }
}
