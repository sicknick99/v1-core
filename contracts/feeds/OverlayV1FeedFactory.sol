// SPDX-License-Identifier: MIT
pragma solidity 0.8.10;

import "../libraries/Oracle.sol";

abstract contract OverlayV1FeedFactory {
    uint256 public immutable microWindow;
    uint256 public immutable macroWindow;

    /// Registry of deployed feeds by factory
    mapping(address => bool) public isFeed;

    /// Event emitted on newly deployed feed
    event FeedDeployed(address indexed user, address feed);

    /// @param _microWindow Micro window to define TWAP over (typically 600s)
    /// @param _macroWindow Macro window to define TWAP over (typically 3600s)
    constructor(uint256 _microWindow, uint256 _macroWindow) {
        microWindow = _microWindow;
        macroWindow = _macroWindow;
    }
}
