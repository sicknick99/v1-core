// SPDX-License-Identifier: MIT
pragma solidity 0.8.10;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@uniswap/v3-core/contracts/interfaces/IUniswapV3Factory.sol";

import "../../interfaces/feeds/uniswapv3/IOverlayV1UniswapV3FeedFactory.sol";

import "../OverlayV1FeedFactory.sol";
import "./OverlayV1UniswapV3Feed.sol";

contract OverlayV1UniswapV3Factory is IOverlayV1UniswapV3FeedFactory, OverlayV1FeedFactory {
    address public immutable ovl;
    address public immutable uniV3Factory;

    // @dev minimum observationCardinality needed for micro and macro windows
    uint16 public immutable observationCardinalityMinimum;

    // registry of feeds; for a given (pool, base, amount, ovlX) pair,
    // returns associated feed
    mapping(address => mapping(address => mapping(uint128 => mapping(address => address))))
        public getFeed;

    constructor(
        address _ovl,
        address _uniV3Factory,
        uint256 _microWindow,
        uint256 _macroWindow,
        uint16 _observationCardinalityMinimum,
        uint256 _averageBlockTime
    ) OverlayV1FeedFactory(_microWindow, _macroWindow) {
        ovl = _ovl;
        uniV3Factory = _uniV3Factory;

        // sanity check on cardinality, given writes happen max once per block
        // SEE: Uniswap/v3-core/blob/main/contracts/libraries/Oracle.sol#L90
        require(
            _averageBlockTime * uint256(_observationCardinalityMinimum) >= _macroWindow,
            "OVLV1: cardinality < macroWindow"
        );
        observationCardinalityMinimum = _observationCardinalityMinimum;
    }

    /// @dev deploys a new feed contract
    /// @dev X is the common currency between market and ovl pools
    /// @return feed_ address of the new feed
    function deployFeed(
        address marketBaseToken,
        address marketQuoteToken,
        uint24 marketFee,
        uint128 marketBaseAmount,
        address ovlXBaseToken,
        address ovlXQuoteToken,
        uint24 ovlXFee
    ) external returns (address feed_) {
        // get the pool address for market tokens
        address marketPool = IUniswapV3Factory(uniV3Factory).getPool(
            marketBaseToken,
            marketQuoteToken,
            marketFee
        );
        require(marketPool != address(0), "OVLV1: !marketPool");

        // get the pool address for ovl/x tokens
        address ovlXPool = IUniswapV3Factory(uniV3Factory).getPool(
            ovlXBaseToken,
            ovlXQuoteToken,
            ovlXFee
        );
        require(ovlXPool != address(0), "OVLV1: !ovlXPool");

        // check feed doesn't already exist
        require(
            getFeed[marketPool][marketBaseToken][marketBaseAmount][ovlXPool] == address(0),
            "OVLV1: feed already exists"
        );

        // Create a new Feed contract
        feed_ = address(
            new OverlayV1UniswapV3Feed(
                marketPool,
                marketBaseToken,
                marketQuoteToken,
                marketBaseAmount,
                ovlXPool,
                ovl,
                microWindow,
                macroWindow,
                observationCardinalityMinimum,
                observationCardinalityMinimum
            )
        );

        // store feed registry record for
        // (marketPool, marketBaseToken, marketBaseAmount, ovlXPool) combo
        // and record address as deployed feed
        getFeed[marketPool][marketBaseToken][marketBaseAmount][ovlXPool] = feed_;
        isFeed[feed_] = true;
        emit FeedDeployed(msg.sender, feed_);
    }
}
