// SPDX-License-Identifier: MIT
pragma solidity ^0.8.29;

import { Test } from "forge-std/Test.sol";
import { IReactive } from "@reactive/src/interfaces/IReactive.sol";
import { CatenaReactive } from "../src/CatenaReactive.sol";
import { MockSystem } from "./Catena.t.sol";

/// Replays 60 synthetic borrower histories (from model/replay.py) through the real contract and compares
/// score and tier after every event. This checks the feature maths, the model, the rules and the clock together.
contract CatenaReplayTest is Test {
    address constant SYS = 0x8888888888888888888888888888888888888888;
    uint256 constant BASE = 84532;
    uint256 constant BASE_TS = 1_700_000_000;
    address pool = address(0xB001);

    CatenaReactive r;
    uint256 txn;

    function setUp() public {
        vm.etch(SYS, address(new MockSystem()).code);
        r = new CatenaReactive(60);
        uint256[] memory ids = new uint256[](1);
        ids[0] = BASE;
        address[] memory pools = new address[](1);
        pools[0] = pool;
        r.setPools(ids, pools);
    }

    function _event(address borrower, uint256 kind, uint256 amtE17, bool late) internal {
        IReactive.LogRecord memory l;
        l.chainId = BASE;
        l.contractAddress = pool;
        l.topic1 = uint256(uint160(borrower));
        l.txHash = ++txn;
        if (kind == 0) {
            l.topic0 = uint256(keccak256("Borrowed(address,uint256,uint256)"));
            l.data = abi.encode(amtE17 * 1e17, uint256(0));
        } else if (kind == 1) {
            l.topic0 = uint256(keccak256("Repaid(address,uint256,bool)"));
            l.data = abi.encode(amtE17 * 1e17, late);
        } else {
            l.topic0 = uint256(keccak256("Defaulted(address)"));
        }
        vm.prank(SYS);
        r.react(l);
    }

    struct Spec {
        uint256[] seq; uint256[] kind; uint256[] amt; uint256[] late; uint256[] dt;
        uint256[] score; uint256[] tier; uint256[] helped; uint256[] hurt;
        int256[] helpedD; int256[] hurtD;
    }

    function _load() internal view returns (Spec memory sp) {
        string memory json = vm.readFile("model/histories.json");
        sp.seq = vm.parseJsonUintArray(json, ".seq");
        sp.kind = vm.parseJsonUintArray(json, ".kind");
        sp.amt = vm.parseJsonUintArray(json, ".amt");
        sp.late = vm.parseJsonUintArray(json, ".late");
        sp.dt = vm.parseJsonUintArray(json, ".dt");
        sp.score = vm.parseJsonUintArray(json, ".score");
        sp.tier = vm.parseJsonUintArray(json, ".tier");
        sp.helped = vm.parseJsonUintArray(json, ".helped");
        sp.hurt = vm.parseJsonUintArray(json, ".hurt");
        sp.helpedD = vm.parseJsonIntArray(json, ".helped_d");
        sp.hurtD = vm.parseJsonIntArray(json, ".hurt_d");
    }

    function _check(Spec memory sp, uint256 i, address b) internal view {
        (,,,,,, uint8 t, uint16 sc,,,,) = r.passports(b);
        assertEq(uint256(t), sp.tier[i], "tier mismatch");
        assertEq(uint256(sc), sp.score[i], "score mismatch");
        (uint8 hp, uint8 ht, int16 hpd, int16 htd, bool isSet) = r.reasons(b);
        if (!isSet) { hp = 6; ht = 6; } // no tier change yet: no reasons
        assertEq(uint256(hp), sp.helped[i], "helped reason mismatch");
        assertEq(uint256(ht), sp.hurt[i], "hurt reason mismatch");
        assertEq(int256(hpd), sp.helpedD[i], "helped delta mismatch");
        assertEq(int256(htd), sp.hurtD[i], "hurt delta mismatch");
    }

    function test_historiesMatchPythonSpec() public {
        Spec memory sp = _load();
        uint256 ts;
        uint256 lastSeq = type(uint256).max;
        for (uint256 i; i < sp.seq.length; ++i) {
            if (sp.seq[i] != lastSeq) { lastSeq = sp.seq[i]; ts = BASE_TS; }
            ts += sp.dt[i];
            vm.warp(ts);
            address b = address(uint160(1000 + sp.seq[i]));
            _event(b, sp.kind[i], sp.amt[i], sp.late[i] == 1);
            _check(sp, i, b);
        }
    }
}
