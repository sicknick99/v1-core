// SPDX-License-Identifier: MIT
pragma solidity 0.8.10;

import "../interfaces/feeds/IOverlayV1FeedFactory.sol";
import "../libraries/Oracle.sol";

abstract contract OverlayV1FeedFactory is IOverlayV1FeedFactory {
    uint256 public immutable microWindow;
    uint256 public immutable macroWindow;

    /// Registry of deployed feeds by factory
    mapping(address => bool) public isFeed;

    /// Event emitted on newly deployed feed
    event FeedDeployed(address indexed user, address feed);

    /// @param _microWindow Micro window to define TWAP over (typically 600s)
    /// @param _macroWindow Macro window to define TWAP over (typically 3600s)
    constructor(uint256 _microWindow, uint256 _macroWindow) {
        // sanity checks on micro and macroWindow
        require(_microWindow > 0, "OVLV1: microWindow == 0");
        require(_macroWindow >= _microWindow, "OVLV1: macroWindow < microWindow");
        require(_macroWindow <= 86400, "OVLV1: macroWindow > 1 day");

        microWindow = _microWindow;
        macroWindow = _macroWindow;
    }
}
