// SPDX-License-Identifier: MIT
pragma solidity ^0.8.29;

import { Test } from "forge-std/Test.sol";
import { Mlp } from "../src/Mlp.sol";

contract MlpHarness {
    function score(int256[6] memory x) external pure returns (uint256) { return Mlp.score(x); }
}

contract MlpTest is Test {
    MlpHarness h = new MlpHarness();
    int256 constant S = 1024;
    // sign per feature: +1 higher is better, -1 higher is worse
    int8[6] SIGN = [int8(1), -1, 1, -1, 1, 1];

    function _x(uint256[] memory flat, uint256 n) internal pure returns (int256[6] memory x) {
        for (uint256 i; i < 6; ++i) x[i] = int256(flat[n * 6 + i]);
    }

    /// Python integer model and Solidity must agree bit for bit on corners and random inputs.
    function test_parityWithPython() public view {
        string memory json = vm.readFile("model/vectors.json");
        uint256[] memory xs = vm.parseJsonUintArray(json, ".x");
        uint256[] memory ys = vm.parseJsonUintArray(json, ".y");
        assertEq(xs.length, ys.length * 6);
        for (uint256 n; n < ys.length; ++n) {
            assertEq(h.score(_x(xs, n)), ys[n], "parity mismatch");
        }
    }

    /// Raising one feature in its good direction never lowers the score (and vice versa).
    function testFuzz_monotone(uint256 seed, uint256 which, uint256 delta) public view {
        int256[6] memory x;
        for (uint256 i; i < 6; ++i) x[i] = int256(uint256(keccak256(abi.encode(seed, i))) % uint256(S + 1));
        uint256 f = which % 6;
        uint256 a = h.score(x);
        int256[6] memory y = x;
        int256 room = SIGN[f] > 0 ? S - x[f] : x[f];
        int256 d = int256(delta % uint256(room + 1));
        y[f] = SIGN[f] > 0 ? x[f] + d : x[f] - d; // move in the "better" direction
        assertGe(h.score(y), a, "better input lowered score");
    }

    /// Extreme and out-of-range inputs saturate instead of overflowing or reverting.
    function test_extremeInputsSaturate() public view {
        int256[6] memory hi; int256[6] memory lo; int256[6] memory wild;
        for (uint256 i; i < 6; ++i) { hi[i] = type(int128).max; lo[i] = type(int128).min; wild[i] = int256(i) * 1e30 - 3e30; }
        assertLe(h.score(hi), uint256(S));
        assertLe(h.score(lo), uint256(S));
        assertLe(h.score(wild), uint256(S));
    }

    /// Worst case for gas: all hidden units active.
    function test_gasOnePass() public {
        int256[6] memory x = [S, int256(0), S, int256(0), S, S];
        uint256 g = gasleft();
        h.score(x);
        emit log_named_uint("gas for one forward pass (incl. call overhead)", g - gasleft());
    }
}
