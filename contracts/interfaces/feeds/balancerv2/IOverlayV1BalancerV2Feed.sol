// SPDX-License-Identifier: MIT
pragma solidity 0.8.10;

// SN TODO: Direct copy from IOverlayV1UniswapV3Feed.sol -> Needs modification to suit the
// OverlayV1BalancerV2Feed.sol contract
import "../IOverlayV1Feed.sol";

interface IOverlayV1BalancerV2Feed is IOverlayV1Feed {
    function marketPool() external view returns (address);

    function ovlWethPool() external view returns (address);

    function ovl() external view returns (address);

    function marketToken0() external view returns (address);

    function marketToken1() external view returns (address);

    function ovlWethToken0() external view returns (address);

    function ovlWethToken1() external view returns (address);

    function marketBaseToken() external view returns (address);

    function marketQuoteToken() external view returns (address);

    function marketBaseAmount() external view returns (uint128);

    /// @dev COPIED AND MODIFIED FROM: Uniswap/v3-periphery/contracts/libraries/OracleLibrary.sol
    function consult(
        address pool,
        uint32[] memory secondsAgos,
        uint32[] memory windows,
        uint256[] memory nowIdxs
    )
        external
        view
        returns (int24[] memory arithmeticMeanTicks_, uint128[] memory harmonicMeanLiquidities_);

    /// @dev COPIED AND MODIFIED FROM: Uniswap/v3-periphery/contracts/libraries/OracleLibrary.sol
    function getQuoteAtTick(
        int24 tick,
        uint128 baseAmount,
        address baseToken,
        address quoteToken
    ) external view returns (uint256 quoteAmount_);

    /// @notice Virtual balance of WETH in the pool in OVL terms
    function getReserveInOvl(
        int24 arithmeticMeanTickMarket,
        uint128 harmonicMeanLiquidityMarket,
        int24 arithmeticMeanTickOvlWeth
    ) external view returns (uint256 reserveInOvl_);

    /// @notice Virtual balance of WETH in the pool
    function getReserveInWeth(int24 arithmeticMeanTickMarket, uint128 harmonicMeanLiquidityMarket)
        external
        view
        returns (uint256 reserveInWeth_);
}
