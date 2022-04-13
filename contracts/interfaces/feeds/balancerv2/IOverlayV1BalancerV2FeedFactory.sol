// SPDX-License-Identifier: MIT
pragma solidity 0.8.10;

import "../IOverlayV1FeedFactory.sol";
import "../../../libraries/balancerv2/BalancerV2Tokens.sol";

interface IOverlayV1BalancerV2FeedFactory is IOverlayV1FeedFactory {
    // immutables
    function ovlWethPool() external view returns (address);

    function ovl() external view returns (address);

    // registry of feeds; for a given (pool, base, quote, amount) pair, returns associated feed
    function getFeed(
        address marketPool,
        address marketBaseToken,
        address marketQuoteToken,
        uint128 marketBaseAmount
    ) external view returns (address feed_);

    /// @dev deploys a new feed contract
    /// @return feed_ address of the new feed
    function deployFeed(
        address marketPool,
        address marketBaseToken,
        address marketQuoteToken,
        uint128 marketBaseAmount,
        BalancerV2Tokens.Info memory balancerV2Tokens
    ) external returns (address feed_);
}
