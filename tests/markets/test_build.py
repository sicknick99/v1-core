from pytest import approx
from brownie.test import given, strategy
from decimal import Decimal
from collections import OrderedDict


def calculate_position_info(oi: Decimal,
                            leverage: Decimal,
                            trading_fee_rate: Decimal,
                            lmbda: Decimal,
                            cap_oi: Decimal) -> (Decimal, Decimal, Decimal,
                                                 Decimal, Decimal):
    collateral = oi / leverage
    impact_fee = 0  # TODO: add in
    trade_fee = oi * trading_fee_rate

    collateral_adjusted = collateral - impact_fee - trade_fee
    oi_adjusted = collateral_adjusted * leverage
    debt = oi_adjusted - collateral_adjusted

    return collateral_adjusted, oi_adjusted, debt, impact_fee, trade_fee


@given(
    oi=strategy('decimal', min_value='0.001', max_value='800000'),
    leverage=strategy('decimal', min_value='1.0', max_value='5.0'),
    is_long=strategy('bool'))
def test_build_creates_position(market, feed, ovl, alice, oi, leverage,
                                is_long):
    expect_pos_id = market.nextPositionId()

    input_collateral = int(oi / leverage * Decimal(1e18))
    input_leverage = int(leverage * Decimal(1e18))
    input_is_long = is_long
    input_min_oi = 0  # NOTE: testing for min_oi below

    # approve market for spending then build
    ovl.approve(market, input_collateral, {"from": alice})
    tx = market.build(input_collateral, input_leverage, input_is_long,
                      input_min_oi, {"from": alice})

    # check position id
    actual_pos_id = tx.return_value
    assert actual_pos_id == expect_pos_id

    # calculate expected pos info data
    trading_fee_rate = Decimal(market.tradingFeeRate() / 1e18)
    lmbda = Decimal(market.lmbda() / 1e18)
    cap_oi = Decimal(market.capOi() / 1e18)
    collateral_adjusted, oi_adjusted, debt, _, _ \
        = calculate_position_info(oi, leverage, trading_fee_rate, lmbda,
                                  cap_oi)

    # calculate expected entry price
    # NOTE: ask(), bid() tested in test_price.py
    data = feed.latest()
    price = market.ask(data) if is_long else market.bid(data)

    # expect values
    expect_leverage = int(leverage * Decimal(1e18))
    expect_is_long = is_long
    expect_entry_price = price
    expect_oi_shares = int(oi_adjusted * Decimal(1e18))
    expect_debt = int(debt * Decimal(1e18))
    expect_cost = int(collateral_adjusted * Decimal(1e18))

    # check position info
    actual_pos = market.positions(actual_pos_id)
    (actual_leverage, actual_is_long, actual_entry_price, actual_oi_shares,
     actual_debt, actual_cost) = actual_pos

    assert actual_leverage == expect_leverage
    assert actual_is_long == expect_is_long
    assert actual_entry_price == expect_entry_price
    assert int(actual_oi_shares) == approx(expect_oi_shares, rel=1e-4)
    assert int(actual_debt) == approx(expect_debt, rel=1e-4)
    assert int(actual_cost) == approx(expect_cost, rel=1e-4)


@given(
    oi=strategy('decimal', min_value='0.001', max_value='800000'),
    leverage=strategy('decimal', min_value='1.0', max_value='5.0'),
    is_long=strategy('bool'))
def test_build_adds_oi(market, feed, ovl, alice, oi, leverage, is_long):
    input_collateral = int(oi / leverage * Decimal(1e18))
    input_leverage = int(leverage * Decimal(1e18))
    input_is_long = is_long
    input_min_oi = 0  # NOTE: testing for min_oi below

    # priors actual values
    _ = market.update({"from": alice})  # update funding prior
    expect_oi = market.oiLong() if is_long else market.oiShort()
    expect_oi_shares = market.oiLongShares() \
        if is_long else market.oiShortShares()

    # approve market for spending then build
    ovl.approve(market, input_collateral, {"from": alice})
    _ = market.build(input_collateral, input_leverage, input_is_long,
                     input_min_oi, {"from": alice})

    # calculate expected oi info data
    trading_fee_rate = Decimal(market.tradingFeeRate() / 1e18)
    lmbda = Decimal(market.lmbda() / 1e18)
    cap_oi = Decimal(market.capOi() / 1e18)
    _, oi_adjusted, _, _, _ = calculate_position_info(oi, leverage,
                                                      trading_fee_rate, lmbda,
                                                      cap_oi)
    expect_oi += int(oi_adjusted * Decimal(1e18))
    expect_oi_shares += int(oi_adjusted * Decimal(1e18))

    # compare with actual aggregate oi values
    actual_oi = market.oiLong() if is_long else market.oiShort()
    actual_oi_shares = market.oiLongShares() if is_long else market.oiShort()

    assert int(actual_oi) == approx(expect_oi, rel=1e-4)
    assert int(actual_oi_shares) == approx(expect_oi_shares, rel=1e-4)


@given(
    oi=strategy('decimal', min_value='0.001', max_value='800000'),
    leverage=strategy('decimal', min_value='1.0', max_value='5.0'),
    is_long=strategy('bool'))
def test_build_executes_transfers(market, feed, ovl, alice, oi, leverage,
                                  is_long):
    input_collateral = int(oi / leverage * Decimal(1e18))
    input_leverage = int(leverage * Decimal(1e18))
    input_is_long = is_long
    input_min_oi = 0  # NOTE: testing for min_oi below

    # approve market for spending then build
    ovl.approve(market, input_collateral, {"from": alice})
    tx = market.build(input_collateral, input_leverage, input_is_long,
                      input_min_oi, {"from": alice})

    # calculate expected info data
    trading_fee_rate = Decimal(market.tradingFeeRate() / 1e18)
    lmbda = Decimal(market.lmbda() / 1e18)
    cap_oi = Decimal(market.capOi() / 1e18)
    _, _, _, impact_fee, trade_fee = calculate_position_info(oi, leverage,
                                                             trading_fee_rate,
                                                             lmbda, cap_oi)

    expect_impact_fee = int(impact_fee * Decimal(1e18))
    expect_trade_fee = int(trade_fee * Decimal(1e18))

    # check Transfer events for:
    # 1. collateral in; 2. impact burn; 3. trade fees out
    assert 'Transfer' in tx.events
    assert len(tx.events['Transfer']) == 3

    # check collateral in event (1)
    assert tx.events['Transfer'][0]['from'] == alice.address
    assert tx.events['Transfer'][0]['to'] == market.address
    assert int(tx.events['Transfer'][0]['value']) == input_collateral

    # check impact burn event (2)
    assert tx.events['Transfer'][1]['from'] == market.address
    assert tx.events['Transfer'][1]['to'] \
        == "0x0000000000000000000000000000000000000000"
    assert int(tx.events['Transfer'][1]['value']) == approx(expect_impact_fee,
                                                            rel=1e-4)

    # check trade fee out event (3)
    assert tx.events['Transfer'][2]['from'] == market.address
    assert tx.events['Transfer'][2]['to'] == market.tradingFeeRecipient()
    assert int(tx.events['Transfer'][2]['value']) == approx(expect_trade_fee,
                                                            rel=1e-4)


@given(
    oi=strategy('decimal', min_value='0.001', max_value='800000'),
    leverage=strategy('decimal', min_value='1.0', max_value='5.0'),
    is_long=strategy('bool'))
def test_build_transfers_collateral_to_market(market, feed, ovl, alice, oi,
                                              leverage, is_long):
    input_collateral = int(oi / leverage * Decimal(1e18))
    input_leverage = int(leverage * Decimal(1e18))
    input_is_long = is_long
    input_min_oi = 0  # NOTE: testing for min_oi below

    # priors actual values
    expect_balance_alice = ovl.balanceOf(alice)
    expect_balance_market = ovl.balanceOf(market)

    # approve market for spending then build
    ovl.approve(market, input_collateral, {"from": alice})
    _ = market.build(input_collateral, input_leverage, input_is_long,
                     input_min_oi, {"from": alice})

    # calculate expected collateral info data
    trading_fee_rate = Decimal(market.tradingFeeRate() / 1e18)
    lmbda = Decimal(market.lmbda() / 1e18)
    cap_oi = Decimal(market.capOi() / 1e18)
    collateral_adjusted, _, _, _, _ = calculate_position_info(oi, leverage,
                                                              trading_fee_rate,
                                                              lmbda, cap_oi)
    expect_balance_alice -= input_collateral
    expect_balance_market += int(collateral_adjusted * Decimal(1e18))

    actual_balance_alice = ovl.balanceOf(alice)
    actual_balance_market = ovl.balanceOf(market)

    assert int(actual_balance_alice) == approx(expect_balance_alice, rel=1e-4)
    assert int(actual_balance_market) == approx(expect_balance_market,
                                                rel=1e-4)
