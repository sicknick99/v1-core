import pytest
from pytest import approx
from brownie import chain, reverts
from brownie.test import given, strategy
from decimal import Decimal
from math import log
from random import randint

from .utils import (
    calculate_position_info,
    get_position_key,
    mid_from_feed,
    entry_from_mid_ratio,
    calculate_mid_ratio,
    RiskParameter
)


# NOTE: Tests passing with isolation fixture
# TODO: Fix tests to pass even without isolation fixture (?)
@pytest.fixture(autouse=True)
def isolation(fn_isolation):
    pass


@given(
    notional=strategy('decimal', min_value='0.001', max_value='80000',
                      places=3),
    leverage=strategy('decimal', min_value='1.0', max_value='5.0', places=3),
    is_long=strategy('bool'))
def test_build_creates_position(market, feed, ovl, alice, notional, leverage,
                                is_long):
    # NOTE: current position id is zero given isolation fixture
    expect_pos_id = 0

    # calculate expected pos info data
    idx_trade = RiskParameter.TRADING_FEE_RATE.value
    trading_fee_rate = Decimal(market.params(idx_trade) / 1e18)
    collateral, notional, debt, trade_fee \
        = calculate_position_info(notional, leverage, trading_fee_rate)

    # input values for tx
    input_collateral = int((collateral) * Decimal(1e18))
    input_leverage = int(leverage * Decimal(1e18))
    input_is_long = is_long

    # NOTE: slippage tests in test_slippage.py
    # NOTE: setting to min/max here, so never reverts with slippage>max
    input_price_limit = 2**256-1 if is_long else 0

    # approve collateral amount: collateral + trade fee
    approve_collateral = int((collateral + trade_fee) * Decimal(1e18))

    # approve market for spending then build
    ovl.approve(market, approve_collateral, {"from": alice})
    tx = market.build(input_collateral, input_leverage, input_is_long,
                      input_price_limit, {"from": alice})

    # check position id
    actual_pos_id = tx.return_value
    assert actual_pos_id == expect_pos_id

    # calculate oi and expected entry price
    # NOTE: ask(), bid() tested in test_price.py
    data = feed.latest()
    mid = Decimal(mid_from_feed(data)) / Decimal(1e18)
    oi = notional / mid

    idx_cap_notional = RiskParameter.CAP_NOTIONAL.value
    cap_notional = Decimal(
        market.capNotionalAdjustedForBounds(
            data, market.params(idx_cap_notional))) \
        / Decimal(1e18)
    cap_oi = (Decimal(cap_notional) / mid)

    volume = int((oi / cap_oi) * Decimal(1e18))  # TODO: circuit breaker adj
    price = market.ask(data, volume) if is_long \
        else market.bid(data, volume)

    # expect values
    expect_is_long = is_long
    expect_liquidated = False
    expect_entry_price = price
    expect_notional_initial = int(notional * Decimal(1e18))
    expect_oi_initial = int(oi * Decimal(1e18))
    expect_debt = int(debt * Decimal(1e18))
    expect_mid_ratio = calculate_mid_ratio(price, int(mid_from_feed(data)))

    # check position info
    expect_pos_key = get_position_key(alice.address, expect_pos_id)
    actual_pos = market.positions(expect_pos_key)
    (actual_notional_initial, actual_debt, actual_mid_ratio,
     actual_is_long, actual_liquidated, actual_oi_initial) = actual_pos

    # calculate the entry price
    mid_price = int(mid_from_feed(data))
    actual_entry_price = entry_from_mid_ratio(actual_mid_ratio, mid_price)

    assert actual_is_long == expect_is_long
    assert actual_liquidated == expect_liquidated
    assert int(actual_entry_price) == approx(expect_entry_price)
    assert int(actual_mid_ratio) == approx(expect_mid_ratio)
    assert int(actual_notional_initial) == approx(expect_notional_initial)
    assert int(actual_oi_initial) == approx(expect_oi_initial)
    assert int(actual_debt) == approx(expect_debt)

    # check build event
    assert "Build" in tx.events
    assert tx.events["Build"]["sender"] == alice.address
    assert tx.events["Build"]["positionId"] == actual_pos_id
    assert tx.events["Build"]["oi"] == actual_oi_initial
    assert tx.events["Build"]["debt"] == actual_debt
    assert tx.events["Build"]["isLong"] == actual_is_long
    assert int(tx.events["Build"]["price"]) == approx(actual_entry_price)


@given(
    notional=strategy('decimal', min_value='0.001', max_value='80000',
                      places=3),
    leverage=strategy('decimal', min_value='1.0', max_value='5.0', places=3),
    is_long=strategy('bool'))
def test_build_adds_oi(market, feed, ovl, alice, notional, leverage, is_long):
    # calculate expected pos info data
    idx_trade = RiskParameter.TRADING_FEE_RATE.value
    trading_fee_rate = Decimal(market.params(idx_trade) / 1e18)
    collateral, notional, debt, trade_fee \
        = calculate_position_info(notional, leverage, trading_fee_rate)

    # input values for tx
    input_collateral = int(collateral * Decimal(1e18))
    input_leverage = int(leverage * Decimal(1e18))
    input_is_long = is_long

    # NOTE: slippage tests in test_slippage.py
    # NOTE: setting to min/max here, so never reverts with slippage>max
    input_price_limit = 2**256-1 if is_long else 0

    # approve collateral amount: collateral + trade fee
    approve_collateral = int((collateral + trade_fee) * Decimal(1e18))

    # priors actual values
    _ = market.update({"from": alice})  # update funding prior
    expect_oi = market.oiLong() if is_long else market.oiShort()
    expect_oi_shares = market.oiLongShares() \
        if is_long else market.oiShortShares()

    # approve market for spending then build
    ovl.approve(market, approve_collateral, {"from": alice})
    _ = market.build(input_collateral, input_leverage, input_is_long,
                     input_price_limit, {"from": alice})

    # calculate oi
    data = feed.latest()
    mid = Decimal(mid_from_feed(data)) / Decimal(1e18)
    oi = notional / mid

    # calculate expected oi info data
    expect_oi += int(oi * Decimal(1e18))
    expect_oi_shares += int(oi * Decimal(1e18))

    # compare with actual aggregate oi values
    actual_oi = market.oiLong() if is_long else market.oiShort()
    actual_oi_shares = market.oiLongShares() if is_long else market.oiShort()

    assert int(actual_oi) == approx(expect_oi)
    assert int(actual_oi_shares) == approx(expect_oi_shares)


def test_build_updates_market(market, ovl, alice):
    # position build attributes
    notional_initial = Decimal(1000)
    leverage = Decimal(1.5)
    is_long = True

    # cache prior timestamp update last value
    prior_timestamp_update_last = market.timestampUpdateLast()

    # mine the chain forward for some time difference with build
    chain.mine(timedelta=600)

    # calculate expected pos info data
    idx_trade = RiskParameter.TRADING_FEE_RATE.value
    trading_fee_rate = Decimal(market.params(idx_trade) / 1e18)
    collateral, _, _, trade_fee \
        = calculate_position_info(notional_initial, leverage, trading_fee_rate)

    # input values for build
    input_collateral = int(collateral * Decimal(1e18))
    input_leverage = int(leverage * Decimal(1e18))
    input_is_long = is_long

    # NOTE: slippage tests in test_slippage.py
    # NOTE: setting to min/max here, so never reverts with slippage>max
    input_price_limit = 2**256-1 if is_long else 0

    # approve collateral amount: collateral + trade fee
    approve_collateral = int((collateral + trade_fee) * Decimal(1e18))

    # approve then build
    # NOTE: build() tests in test_build.py
    ovl.approve(market, approve_collateral, {"from": alice})
    tx = market.build(input_collateral, input_leverage, input_is_long,
                      input_price_limit, {"from": alice})

    # get the expected timestamp and check equal to actual
    expect_timestamp_update_last = chain[tx.block_number]['timestamp']
    actual_timestamp_update_last = market.timestampUpdateLast()

    assert actual_timestamp_update_last == expect_timestamp_update_last
    assert actual_timestamp_update_last != prior_timestamp_update_last


@given(
    notional=strategy('decimal', min_value='0.001', max_value='80000',
                      places=3),
    leverage=strategy('decimal', min_value='1.0', max_value='5.0', places=3),
    is_long=strategy('bool'))
def test_build_registers_volume(market, feed, ovl, alice, notional, leverage,
                                is_long):
    # calculate expected pos info data
    idx_trade = RiskParameter.TRADING_FEE_RATE.value
    trading_fee_rate = Decimal(market.params(idx_trade) / 1e18)
    collateral, notional, debt, trade_fee \
        = calculate_position_info(notional, leverage, trading_fee_rate)

    # input values for the tx
    input_collateral = int(collateral * Decimal(1e18))
    input_leverage = int(leverage * Decimal(1e18))
    input_is_long = is_long

    # NOTE: slippage tests in test_slippage.py
    # NOTE: setting to min/max here, so never reverts with slippage>max
    input_price_limit = 2**256-1 if is_long else 0

    # approve collateral amount: collateral + trade fee
    approve_collateral = int((collateral + trade_fee) * Decimal(1e18))

    # update funding prior
    _ = market.update({"from": alice})

    # priors actual values. longs get the ask, shorts get the bid on build
    snapshot_volume = market.snapshotVolumeAsk() if is_long else \
        market.snapshotVolumeBid()
    last_timestamp, last_window, last_volume = snapshot_volume

    # approve market for spending then build
    ovl.approve(market, approve_collateral, {"from": alice})
    tx = market.build(input_collateral, input_leverage, input_is_long,
                      input_price_limit, {"from": alice})

    # calculate expected rolling volume and window numbers when
    # adjusted for decay
    # NOTE: decayOverWindow() tested in test_rollers.py
    data = feed.latest()
    _, micro_window, _, _, _, _, _, _ = data
    mid = Decimal(mid_from_feed(data)) / Decimal(1e18)

    oi = notional / mid
    idx_cap_notional = RiskParameter.CAP_NOTIONAL.value
    cap_notional = Decimal(
        market.capNotionalAdjustedForBounds(
            data, market.params(idx_cap_notional))/1e18)
    cap_oi = cap_notional / mid

    input_volume = int((oi / cap_oi) * Decimal(1e18))
    input_window = micro_window
    input_timestamp = chain[tx.block_number]['timestamp']

    # expect accumulator now to be calculated as
    # accumulatorLast * (1 - dt/windowLast) + value
    dt = input_timestamp - last_timestamp
    last_volume_decayed = last_volume * (1 - dt/last_window) \
        if last_window != 0 and dt >= last_window else 0
    expect_volume = int(last_volume_decayed + input_volume)

    # expect window now to be calculated as weighted average
    # of remaining time left in last window and total time in new window
    # weights are accumulator values for the respective time window
    numerator = int((last_window - dt) * last_volume_decayed
                    + input_window * input_volume)
    expect_window = int(numerator / expect_volume)
    expect_timestamp = input_timestamp

    # compare with actual rolling volume, timestamp last, window last values
    actual = market.snapshotVolumeAsk() if is_long else \
        market.snapshotVolumeBid()

    actual_timestamp, actual_window, actual_volume = actual
    assert actual_timestamp == expect_timestamp
    assert int(actual_window) == approx(expect_window, abs=1)  # tol to 1s
    assert int(actual_volume) == approx(expect_volume)


@given(
    notional=strategy('decimal', min_value='0.001', max_value='80000',
                      places=3),
    leverage=strategy('decimal', min_value='1.0', max_value='5.0', places=3),
    is_long=strategy('bool'))
def test_build_executes_transfers(market, factory, ovl, alice, notional,
                                  leverage, is_long):
    # calculate expected pos info data
    idx_trade = RiskParameter.TRADING_FEE_RATE.value
    trading_fee_rate = Decimal(market.params(idx_trade) / 1e18)
    collateral, notional, debt, trade_fee \
        = calculate_position_info(notional, leverage, trading_fee_rate)

    # input values for the tx
    input_collateral = int(collateral * Decimal(1e18))
    input_leverage = int(leverage * Decimal(1e18))
    input_is_long = is_long

    # NOTE: slippage tests in test_slippage.py
    # NOTE: setting to min/max here, so never reverts with slippage>max
    input_price_limit = 2**256-1 if is_long else 0

    # approve collateral amount: collateral + trade fee
    # amount of collateral that will be transferred in
    approve_collateral = int((collateral + trade_fee) * Decimal(1e18))

    # approve market for spending then build
    ovl.approve(market, approve_collateral, {"from": alice})
    tx = market.build(input_collateral, input_leverage, input_is_long,
                      input_price_limit, {"from": alice})

    # expected values
    expect_collateral_in = approve_collateral
    expect_trade_fee = int(trade_fee * Decimal(1e18))

    # check Transfer events for:
    # 1. collateral in; 2. trade fees out
    assert 'Transfer' in tx.events
    assert len(tx.events['Transfer']) == 2

    # check collateral in event (1)
    assert tx.events['Transfer'][0]['from'] == alice.address
    assert tx.events['Transfer'][0]['to'] == market.address
    assert int(tx.events['Transfer'][0]['value']) == \
        approx(expect_collateral_in)

    # check trade fee out event (2)
    assert tx.events['Transfer'][1]['from'] == market.address
    assert tx.events['Transfer'][1]['to'] == factory.feeRecipient()
    assert int(tx.events['Transfer'][1]['value']) == approx(expect_trade_fee)


@given(
    notional=strategy('decimal', min_value='0.001', max_value='80000',
                      places=3),
    leverage=strategy('decimal', min_value='1.0', max_value='5.0', places=3),
    is_long=strategy('bool'))
def test_build_transfers_collateral_to_market(market, ovl, alice, notional,
                                              leverage, is_long):
    # calculate expected pos info data
    idx_trade = RiskParameter.TRADING_FEE_RATE.value
    trading_fee_rate = Decimal(market.params(idx_trade) / 1e18)
    collateral, notional, debt, trade_fee \
        = calculate_position_info(notional, leverage, trading_fee_rate)

    # input values for the tx
    input_collateral = int(collateral * Decimal(1e18))
    input_leverage = int(leverage * Decimal(1e18))
    input_is_long = is_long

    # NOTE: slippage tests in test_slippage.py
    # NOTE: setting to min/max here, so never reverts with slippage>max
    input_price_limit = 2**256-1 if is_long else 0

    # approve collateral amount: collateral + trade fee
    # amount of collateral that will be transferred in
    approve_collateral = int((collateral + trade_fee) * Decimal(1e18))

    # priors actual values
    expect_balance_alice = ovl.balanceOf(alice)
    expect_balance_market = ovl.balanceOf(market)

    # approve market for spending then build
    ovl.approve(market, approve_collateral, {"from": alice})
    _ = market.build(input_collateral, input_leverage, input_is_long,
                     input_price_limit, {"from": alice})

    # calculate expected collateral info data
    expect_collateral_in = int((collateral + trade_fee) * Decimal(1e18))
    expect_balance_alice -= expect_collateral_in
    expect_balance_market += int(collateral * Decimal(1e18))

    actual_balance_alice = ovl.balanceOf(alice)
    actual_balance_market = ovl.balanceOf(market)

    assert int(actual_balance_alice) == approx(expect_balance_alice)
    assert int(actual_balance_market) == approx(expect_balance_market)


@given(
    notional=strategy('decimal', min_value='0.001', max_value='80000',
                      places=3),
    leverage=strategy('decimal', min_value='1.0', max_value='5.0', places=3),
    is_long=strategy('bool'))
def test_build_transfers_trading_fees(market, factory, ovl, alice, notional,
                                      leverage, is_long):
    # calculate expected pos info data
    idx_trade = RiskParameter.TRADING_FEE_RATE.value
    trading_fee_rate = Decimal(market.params(idx_trade) / 1e18)
    collateral, notional, debt, trade_fee \
        = calculate_position_info(notional, leverage, trading_fee_rate)

    # input values for the tx
    input_collateral = int(collateral * Decimal(1e18))
    input_leverage = int(leverage * Decimal(1e18))
    input_is_long = is_long

    # NOTE: slippage tests in test_slippage.py
    # NOTE: setting to min/max here, so never reverts with slippage>max
    input_price_limit = 2**256-1 if is_long else 0

    # approve collateral amount: collateral + trade fee
    # amount of collateral that will be transferred in
    approve_collateral = int((collateral + trade_fee) * Decimal(1e18))

    # priors actual values
    recipient = factory.feeRecipient()
    expect = ovl.balanceOf(recipient)

    # approve market for spending then build
    ovl.approve(market, approve_collateral, {"from": alice})
    _ = market.build(input_collateral, input_leverage, input_is_long,
                     input_price_limit, {"from": alice})

    expect += int(trade_fee * Decimal(1e18))
    actual = ovl.balanceOf(recipient)

    assert int(actual) == approx(expect)


def test_build_reverts_when_leverage_less_than_one(market, ovl, alice):
    # NOTE: current position id is zero given isolation fixture
    expect_pos_id = 0

    input_collateral = int(100 * Decimal(1e18))
    input_is_long = True

    # NOTE: slippage tests in test_slippage.py
    # NOTE: setting to min/max here, so never reverts with slippage>max
    input_price_limit = 2**256-1 if input_is_long else 0

    # approve market for spending before build
    ovl.approve(market, 2**256-1, {"from": alice})

    # check build reverts when input leverage is less than one (ONE = 1e18)
    input_leverage = int(Decimal(1e18) - 1)
    with reverts("OVLV1:lev<min"):
        _ = market.build(input_collateral, input_leverage, input_is_long,
                         input_price_limit, {"from": alice})

    # check build succeeds when input leverage is equal to one
    input_leverage = int(Decimal(1e18))
    tx = market.build(input_collateral, input_leverage, input_is_long,
                      input_price_limit, {"from": alice})

    # check position id
    actual_pos_id = tx.return_value
    assert expect_pos_id == actual_pos_id


def test_build_reverts_when_leverage_greater_than_cap(market, ovl, alice):
    # NOTE: current position id is zero given isolation fixture
    expect_pos_id = 0

    input_collateral = int(100 * Decimal(1e18))
    input_is_long = True

    # NOTE: slippage tests in test_slippage.py
    # NOTE: setting to min/max here, so never reverts with slippage>max
    input_price_limit = 2**256-1 if input_is_long else 0

    # approve market for spending before build. Use the max just for here
    ovl.approve(market, 2**256 - 1, {"from": alice})

    # check build reverts when input leverage is less than one (ONE = 1e18)
    cap_leverage = market.params(RiskParameter.CAP_LEVERAGE.value)
    input_leverage = cap_leverage + 1
    with reverts("OVLV1:lev>max"):
        _ = market.build(input_collateral, input_leverage, input_is_long,
                         input_price_limit, {"from": alice})

    # check build succeeds when input leverage is equal to cap
    input_leverage = cap_leverage
    tx = market.build(input_collateral, input_leverage, input_is_long,
                      input_price_limit, {"from": alice})

    # check position id
    actual_pos_id = tx.return_value
    assert expect_pos_id == actual_pos_id


@given(
    leverage=strategy('decimal', min_value='1.0', max_value='5.0', places=3),
    is_long=strategy('bool'))
def test_build_reverts_when_collateral_less_than_min(market, ovl, alice,
                                                     leverage, is_long):
    # NOTE: current position id is zero given isolation fixture
    expect_pos_id = 0
    min_collateral = market.params(RiskParameter.MIN_COLLATERAL.value)

    input_leverage = int(leverage * Decimal(1e18))
    input_is_long = is_long
    input_collateral = min_collateral - 1

    # NOTE: slippage tests in test_slippage.py
    # NOTE: setting to min/max here, so never reverts with slippage>max
    input_price_limit = 2**256-1 if is_long else 0

    # approve market for spending then build. use max
    ovl.approve(market, 2**256 - 1, {"from": alice})

    # check build reverts for min_collat > collat
    with reverts("OVLV1:collateral<min"):
        _ = market.build(input_collateral, input_leverage, input_is_long,
                         input_price_limit, {"from": alice})

    # check build succeeds for min_collat <= collat
    input_collateral = min_collateral
    tx = market.build(input_collateral, input_leverage, input_is_long,
                      input_price_limit, {"from": alice})

    # check position id
    actual_pos_id = tx.return_value
    assert expect_pos_id == actual_pos_id


@given(is_long=strategy('bool'))
def test_build_reverts_when_oi_greater_than_cap(market, ovl, alice, is_long):
    # NOTE: current position id is zero given isolation fixture
    expect_pos_id = 0

    input_leverage = int(1e18)
    input_is_long = is_long

    tol = 1e-4

    # NOTE: slippage tests in test_slippage.py
    # NOTE: setting to min/max here, so never reverts with slippage>max
    input_price_limit = 2**256-1 if is_long else 0

    # approve market for spending before build. use max
    ovl.approve(market, 2**256 - 1, {"from": alice})

    # check build reverts when notional is greater than static cap
    cap_notional = market.params(RiskParameter.CAP_NOTIONAL.value)
    input_collateral = cap_notional * (1 + tol)
    with reverts("OVLV1:oi>cap"):
        _ = market.build(input_collateral, input_leverage, input_is_long,
                         input_price_limit, {"from": alice})

    # check build succeeds when notional is less than static cap
    input_collateral = cap_notional * (1 - tol)
    tx = market.build(input_collateral, input_leverage, input_is_long,
                      input_price_limit, {"from": alice})

    # check position id
    actual_pos_id = tx.return_value
    assert expect_pos_id == actual_pos_id


# NOTE: use mock_market so price doesn't move during test
@given(is_long=strategy('bool'))
def test_build_reverts_when_liquidatable(mock_market, feed, ovl, alice,
                                         is_long):
    idx_delta = RiskParameter.DELTA.value
    idx_lmbda = RiskParameter.LMBDA.value
    idx_mmf = RiskParameter.MAINTENANCE_MARGIN_FRACTION.value
    idx_liq = RiskParameter.LIQUIDATION_FEE_RATE.value

    # NOTE: current position id is zero given isolation fixture
    expect_pos_id = 0
    leverage = Decimal(5)

    tol = 1e-3

    # priors
    delta = Decimal(mock_market.params(idx_delta)) / Decimal(1e18)
    lmbda = Decimal(mock_market.params(idx_lmbda)) / Decimal(1e18)
    maintenance_fraction = Decimal(mock_market.params(idx_mmf)) / Decimal(1e18)
    liq_fee_rate = Decimal(mock_market.params(idx_liq)) / Decimal(1e18)

    # Use mid price to calculate liquidation price
    data = feed.latest()
    mid_price = Decimal(mid_from_feed(data))

    # calculate the liquidation price
    # then infer market impact required to slip to this price
    # ask = mid * (1 - mm) + 1/L
    # bid = mid * (1 + mm) - 1/L
    if is_long:
        entry_price = mid_price \
            * (1 - maintenance_fraction / (1 - liq_fee_rate)
               + Decimal(1)/leverage)
    else:
        entry_price = mid_price \
            * (1 + maintenance_fraction / (1 - liq_fee_rate)
               - Decimal(1)/leverage)

    # will be liquidatable already when
    # ask = mid * e **(delta + lmbda * volume)
    # bid = mid * e**(-delta - lmbda * volume)
    if is_long:
        volume = (Decimal(log(entry_price / mid_price)) - delta) / lmbda
    else:
        volume = Decimal(-1) \
            * (Decimal(log(entry_price / mid_price)) + delta) / lmbda

    # calculate notional from required market impact
    idx_cap_notional = RiskParameter.CAP_NOTIONAL.value
    cap_notional = mock_market.capNotionalAdjustedForBounds(
        data, mock_market.params(idx_cap_notional))

    input_leverage = int(leverage * Decimal(1e18))
    input_is_long = is_long

    # NOTE: slippage tests in test_slippage.py
    # NOTE: setting to min/max here, so never reverts with slippage>max
    input_price_limit = 2**256-1 if is_long else 0

    # approve market for spending before build. use max
    ovl.approve(mock_market, 2**256 - 1, {"from": alice})

    # check build reverts when position is liquidatable
    input_notional = Decimal(cap_notional) * volume * Decimal(1 + tol)
    input_collateral = int((input_notional / leverage))
    with reverts("OVLV1:liquidatable"):
        _ = mock_market.build(input_collateral, input_leverage, input_is_long,
                              input_price_limit, {"from": alice})

    # check build succeeds when position is not liquidatable
    input_notional = Decimal(cap_notional) * volume * Decimal(1 - tol)
    input_collateral = int(input_notional / leverage)
    tx = mock_market.build(input_collateral, input_leverage, input_is_long,
                           input_price_limit, {"from": alice})

    # check position id
    assert tx.return_value == expect_pos_id


def test_build_reverts_when_oi_zero(mock_market, mock_feed, ovl, alice, bob):
    # NOTE: current position id is zero given isolation fixture
    expect_pos_id = 0

    input_collateral = int(1e18)
    input_leverage = int(1e18)
    input_is_long = True

    tol = 1e-4

    # NOTE: slippage tests in test_slippage.py
    # NOTE: setting to min/max here, so never reverts with slippage>max
    input_price_limit = 2**256-1

    # approve market for spending before build. use max
    ovl.approve(mock_market, 2**256 - 1, {"from": alice})

    # check build reverts when price so large that
    # notional / price rounds down to zero
    price = int(Decimal(input_collateral)
                * Decimal(input_leverage) * Decimal(1 + tol))
    mock_feed.setPrice(price, {"from": bob})

    with reverts("OVLV1:oi==0"):
        _ = mock_market.build(input_collateral, input_leverage, input_is_long,
                              input_price_limit, {"from": alice})

    # check build succeeds when price is below rounding limit
    price = int(Decimal(input_collateral)
                * Decimal(input_leverage) * Decimal(1 - tol))

    mock_feed.setPrice(price, {"from": bob})
    tx = mock_market.build(input_collateral, input_leverage, input_is_long,
                           input_price_limit, {"from": alice})

    # check position id
    actual_pos_id = tx.return_value
    assert expect_pos_id == actual_pos_id


def test_multiple_build_creates_multiple_positions(market, factory, ovl,
                                                   feed, alice, bob):
    # loop through 10 times
    n = 10
    total_notional_long = Decimal(10000)
    total_notional_short = Decimal(7500)

    # set k to zero to avoid funding calcs
    market.setRiskParam(RiskParameter.K.value, 0, {"from": factory})

    # alice goes long and bob goes short n times
    input_total_notional_long = total_notional_long * Decimal(1e18)
    input_total_notional_short = total_notional_short * Decimal(1e18)

    # NOTE: current position id is zero given isolation fixture
    expect_pos_id = 0

    # calculate expected pos info data
    trading_fee_rate = Decimal(
        market.params(RiskParameter.TRADING_FEE_RATE.value) / 1e18)
    leverage_cap = Decimal(
        market.params(RiskParameter.CAP_LEVERAGE.value) / 1e18)

    # approve collateral amount: collateral + trade fee
    approve_collateral_alice = int((input_total_notional_long
                                    * (1 + trading_fee_rate)))
    approve_collateral_bob = int((input_total_notional_short
                                  * (1 + trading_fee_rate)))

    # approve market for spending then build
    ovl.approve(market, approve_collateral_alice, {"from": alice})
    ovl.approve(market, approve_collateral_bob, {"from": bob})

    # per trade notional values
    notional_alice = total_notional_long / Decimal(n)
    notional_bob = total_notional_short / Decimal(n)
    is_long_alice = True
    is_long_bob = False

    for i in range(n):
        chain.mine(timedelta=60)

        # choose a random leverage
        leverage_alice = randint(1, leverage_cap)
        leverage_bob = randint(1, leverage_cap)

        # calculate collateral amounts
        collateral_alice, _, debt_alice, _ = calculate_position_info(
            notional_alice, leverage_alice, trading_fee_rate)
        collateral_bob, _, debt_bob, _ = calculate_position_info(
            notional_bob, leverage_bob, trading_fee_rate)

        input_collateral_alice = int(collateral_alice * Decimal(1e18))
        input_collateral_bob = int(collateral_bob * Decimal(1e18))
        input_leverage_alice = int(leverage_alice * Decimal(1e18))
        input_leverage_bob = int(leverage_bob * Decimal(1e18))

        # NOTE: slippage tests in test_slippage.py
        # NOTE: setting to min/max here, so never reverts with slippage>max
        input_price_limit_alice = 2**256-1 if is_long_alice else 0
        input_price_limit_bob = 2**256-1 if is_long_bob else 0

        # cache price, liquidity data from feed
        data = feed.latest()
        mid_price = mid_from_feed(data)

        # cache current aggregate long oi for comparison later
        expect_oi_long = market.oiLong()

        # build position for alice
        tx_alice = market.build(input_collateral_alice, input_leverage_alice,
                                is_long_alice, input_price_limit_alice,
                                {"from": alice})

        actual_pos_id_alice = tx_alice.return_value
        expect_pos_id_alice = expect_pos_id

        assert actual_pos_id_alice == expect_pos_id_alice

        # check position info for alice for everything
        # except price to avoid impact calcs
        expect_notional_alice = int(notional_alice * Decimal(1e18))
        expect_oi_alice = int(Decimal(expect_notional_alice) * Decimal(1e18)
                              / Decimal(mid_price))
        expect_debt_alice = int(debt_alice * Decimal(1e18))
        expect_is_long_alice = is_long_alice
        expect_liquidated_alice = False
        actual_pos_alice = market.positions(
            get_position_key(alice.address, expect_pos_id_alice))

        (actual_notional_alice, actual_debt_alice, actual_mid_ratio_alice,
         actual_is_long_alice, actual_liquidated_alice,
         actual_oi_alice) = actual_pos_alice

        assert actual_is_long_alice == expect_is_long_alice
        assert actual_liquidated_alice == expect_liquidated_alice
        assert int(actual_notional_alice) == approx(expect_notional_alice)
        assert int(actual_oi_alice) == approx(expect_oi_alice, rel=1e-3)
        assert int(actual_debt_alice) == approx(expect_debt_alice)

        # check oi added to long side by alice
        expect_oi_long += expect_oi_alice
        actual_oi_long = market.oiLong()

        assert int(actual_oi_long) == approx(expect_oi_long, rel=1e-3)

        # increment expect position id
        expect_pos_id += 1

        # cache price, liquidity data from feed
        data = feed.latest()
        mid_price = mid_from_feed(data)

        # cache current aggregate short oi for comparison later
        expect_oi_short = market.oiShort()

        # build position for bob
        tx_bob = market.build(input_collateral_bob, input_leverage_bob,
                              is_long_bob, input_price_limit_bob,
                              {"from": bob})

        actual_pos_id_bob = tx_bob.return_value
        expect_pos_id_bob = expect_pos_id
        assert actual_pos_id_bob == expect_pos_id_bob

        # check position info for bob for everything
        # except price to avoid impact calcs
        expect_notional_bob = int(notional_bob * Decimal(1e18))
        expect_oi_bob = int(Decimal(expect_notional_bob) * Decimal(1e18)
                            / Decimal(mid_price))
        expect_debt_bob = int(debt_bob * Decimal(1e18))
        expect_is_long_bob = is_long_bob
        expect_liquidated_bob = False
        actual_pos_bob = market.positions(
            get_position_key(bob.address, expect_pos_id_bob))

        (actual_notional_bob, actual_debt_bob, actual_mid_ratio_bob,
         actual_is_long_bob, actual_liquidated_bob,
         actual_oi_bob) = actual_pos_bob

        assert actual_is_long_bob == expect_is_long_bob
        assert actual_liquidated_bob is expect_liquidated_bob
        assert int(actual_notional_bob) == approx(expect_notional_bob)
        assert int(actual_oi_bob) == approx(expect_oi_bob, rel=1e-3)
        assert int(actual_debt_bob) == approx(expect_debt_bob)

        # check oi added to short side by bob
        expect_oi_short += expect_oi_bob
        actual_oi_short = market.oiShort()

        assert int(actual_oi_short) == approx(expect_oi_short, rel=1e-3)

        # increment expect position id
        expect_pos_id += 1
