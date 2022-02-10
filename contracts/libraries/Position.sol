// SPDX-License-Identifier: MIT
pragma solidity 0.8.10;

import "@openzeppelin/contracts/utils/math/Math.sol";
import "./FixedPoint.sol";

library Position {
    using FixedPoint for uint256;
    uint256 internal constant ONE = 1e18;

    struct Info {
        uint120 oiShares; // initial open interest
        uint120 debt; // debt
        bool isLong; // whether long or short
        bool liquidated; // whether has been liquidated
        uint256 entryPrice; // price received at entry
    }

    /*///////////////////////////////////////////////////////////////
                        POSITIONS MAPPING FUNCTIONS
    //////////////////////////////////////////////////////////////*/

    /// @notice Retrieves a position from positions mapping
    function get(
        mapping(bytes32 => Info) storage self,
        address owner,
        uint256 id
    ) internal view returns (Info storage position_) {
        position_ = self[keccak256(abi.encodePacked(owner, id))];
    }

    /// @notice Stores a position in positions mapping
    function set(
        mapping(bytes32 => Info) storage self,
        address owner,
        uint256 id,
        Info memory position
    ) internal {
        self[keccak256(abi.encodePacked(owner, id))] = position;
    }

    /*///////////////////////////////////////////////////////////////
                    POSITION GETTER FUNCTIONS
    //////////////////////////////////////////////////////////////*/

    /// @notice Computes the position's initial open interest cast to uint256
    function _oiShares(Info memory self) private pure returns (uint256) {
        return uint256(self.oiShares);
    }

    /// @notice Computes the position's debt cast to uint256
    function _debt(Info memory self) private pure returns (uint256) {
        return uint256(self.debt);
    }

    /// @notice Whether the position exists
    /// @dev Is false if position has been liquidated or has zero oi
    function exists(Info memory self) internal pure returns (bool exists_) {
        return (!self.liquidated && self.oiShares > 0);
    }

    /*///////////////////////////////////////////////////////////////
                        POSITION CALC FUNCTIONS
    //////////////////////////////////////////////////////////////*/

    /// @notice Computes the current shares of open interest position holds
    /// @notice on pos.isLong side of the market
    function oiSharesCurrent(Info memory self, uint256 fraction) internal pure returns (uint256) {
        return _oiShares(self).mulDown(fraction);
    }

    /// @notice Computes the current debt position holds
    function debtCurrent(Info memory self, uint256 fraction) internal pure returns (uint256) {
        return _debt(self).mulDown(fraction);
    }

    /// @notice Computes the initial open interest the position had when built
    function oiInitial(Info memory self, uint256 fraction) internal pure returns (uint256) {
        return _oiShares(self).mulDown(fraction);
    }

    /// @notice Computes the current open interest of a position accounting for
    /// @notice potential funding payments between long/short sides
    /// @dev returns zero when oiShares = totalOi = totalOiShares = 0 to avoid
    /// @dev div by zero errors
    function oiCurrent(
        Info memory self,
        uint256 fraction,
        uint256 totalOi,
        uint256 totalOiShares
    ) internal pure returns (uint256) {
        uint256 posOiShares = oiSharesCurrent(self, fraction);
        if (posOiShares == 0 || totalOi == 0) return 0;
        return posOiShares.mulDown(totalOi).divUp(totalOiShares);
    }

    /// @notice Computes the position's cost cast to uint256
    /// WARNING: be careful modifying oi and debt on unwind
    function cost(Info memory self, uint256 fraction) internal pure returns (uint256) {
        uint256 posOiShares = oiSharesCurrent(self, fraction);
        uint256 posDebt = debtCurrent(self, fraction);
        return posOiShares - posDebt;
    }

    /// @notice Computes the value of a position
    /// @dev Floors to zero, so won't properly compute if self is underwater
    function value(
        Info memory self,
        uint256 fraction,
        uint256 totalOi,
        uint256 totalOiShares,
        uint256 currentPrice,
        uint256 capPayoff
    ) internal pure returns (uint256 val_) {
        uint256 posOi = oiCurrent(self, fraction, totalOi, totalOiShares);
        uint256 posDebt = debtCurrent(self, fraction);
        uint256 entryPrice = self.entryPrice;

        if (self.isLong) {
            // oi - debt + oi * min(ratioPrice - 1, capPayoff)
            // = oi - debt + oi * [min(ratioPrice, 1 + capPayoff) - 1]
            // = oi * min(ratioPrice, 1 + capPayoff) - debt
            val_ = posOi.mulUp(currentPrice).divDown(entryPrice);
            val_ = Math.min(val_, posOi.mulUp(ONE + capPayoff));
            val_ -= Math.min(val_, posDebt); // floor to 0
        } else {
            // NOTE: capPayoff >= 1, so no need to include w short
            // oi - debt - oi * (ratioPrice - 1)
            // = 2 * oi - [ debt + oi * ratioPrice ]
            val_ = posOi.mulDown(2 * ONE);
            // floor to 0
            val_ -= Math.min(val_, posDebt + posOi.mulUp(currentPrice).divDown(entryPrice));
        }
    }

    /// @notice Computes the notional of a position
    /// @dev Floors to debt if value <= 0
    function notional(
        Info memory self,
        uint256 fraction,
        uint256 totalOi,
        uint256 totalOiShares,
        uint256 currentPrice,
        uint256 capPayoff
    ) internal pure returns (uint256 notional_) {
        uint256 posValue = value(self, fraction, totalOi, totalOiShares, currentPrice, capPayoff);
        uint256 posDebt = debtCurrent(self, fraction);
        notional_ = posValue + posDebt;
    }

    /// @notice Computes the trading fees to be imposed on a position for build/unwind
    function tradingFee(
        Info memory self,
        uint256 fraction,
        uint256 totalOi,
        uint256 totalOiShares,
        uint256 currentPrice,
        uint256 capPayoff,
        uint256 tradingFeeRate
    ) internal pure returns (uint256 tradingFee_) {
        uint256 posNotional = notional(
            self,
            fraction,
            totalOi,
            totalOiShares,
            currentPrice,
            capPayoff
        );
        tradingFee_ = posNotional.mulUp(tradingFeeRate);
    }

    /// @notice Whether a position can be liquidated
    /// @dev is true when value < maintenance margin
    function isLiquidatable(
        Info memory self,
        uint256 totalOi,
        uint256 totalOiShares,
        uint256 currentPrice,
        uint256 capPayoff,
        uint256 marginMaintenance
    ) internal pure returns (bool can_) {
        uint256 fraction = ONE;
        uint256 posOiInitial = oiInitial(self, fraction);

        if (self.liquidated || posOiInitial == 0) {
            // already been liquidated
            return false;
        }

        uint256 val = value(self, fraction, totalOi, totalOiShares, currentPrice, capPayoff);
        uint256 maintenanceMargin = posOiInitial.mulUp(marginMaintenance);
        can_ = val < maintenanceMargin;
    }

    /// @notice Computes the liquidation price of a position
    /// @dev price when value = maintenance margin
    function liquidationPrice(
        Info memory self,
        uint256 totalOi,
        uint256 totalOiShares,
        uint256 marginMaintenance
    ) internal pure returns (uint256 liqPrice_) {
        uint256 fraction = ONE;
        uint256 posOiCurrent = oiCurrent(self, fraction, totalOi, totalOiShares);
        uint256 posOiInitial = oiInitial(self, fraction);
        uint256 posDebt = debtCurrent(self, fraction);

        if (self.liquidated || posOiInitial == 0 || posOiCurrent == 0) {
            // return 0 if already liquidated or no oi left in position
            return 0;
        }

        uint256 oiFrame = posOiInitial.mulUp(marginMaintenance).add(posDebt).divDown(posOiCurrent);

        if (self.isLong) {
            liqPrice_ = self.entryPrice.mulUp(oiFrame);
        } else {
            liqPrice_ = self.entryPrice.mulUp((2 * ONE).sub(oiFrame));
        }
    }
}
