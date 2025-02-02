from decimal import Decimal
from math import exp

from .utils import RiskParameter


def test_data_is_valid(market, rando):
    tx = market.update({"from": rando})
    data = tx.return_value
    idx = RiskParameter.PRICE_DRIFT_UPPER_LIMIT.value

    _, _, _, _, price_macro_now, price_macro_ago, _, _ = data
    drift = (market.params(idx) / Decimal(1e18))

    dp = price_macro_now / price_macro_ago
    dp_lower_limit = exp(-drift * 3000)
    dp_upper_limit = exp(drift * 3000)

    expect = (dp >= dp_lower_limit and dp <= dp_upper_limit)
    actual = market.dataIsValid(data)
    assert expect == actual


def test_data_is_valid_when_dp_less_than_lower_limit(market):
    tol = 1e-04
    idx = RiskParameter.PRICE_DRIFT_UPPER_LIMIT.value
    drift = (market.params(idx) / Decimal(1e18))

    price_now = 2562676671798193257266

    # check data is not valid when price is less than lower limit
    pow = Decimal(drift) * Decimal(3000) * Decimal(1+tol)
    price_ago = int(price_now * exp(pow))
    data = (1643583611, 600, 3000, 2569091057405103628119,
            price_now, price_ago,
            4677792160494647834844974, True)

    expect = False
    actual = market.dataIsValid(data)
    assert expect == actual

    # check data is valid when price is just above the lower limit
    pow = Decimal(drift) * Decimal(3000) * Decimal(1-tol)
    price_ago = int(price_now * exp(pow))
    data = (1643583611, 600, 3000, 2569091057405103628119,
            price_now, price_ago,
            4677792160494647834844974, True)

    expect = True
    actual = market.dataIsValid(data)
    assert expect == actual


def test_data_is_valid_when_dp_greater_than_upper_limit(market):
    tol = 1e-04
    idx = RiskParameter.PRICE_DRIFT_UPPER_LIMIT.value
    drift = (market.params(idx) / Decimal(1e18))

    price_ago = 2562676671798193257266

    # check data is not valid when price is greater than upper limit
    pow = Decimal(drift) * Decimal(3000) * Decimal(1+tol)
    price_now = int(price_ago * exp(pow))
    data = (1643583611, 600, 3000, 2569091057405103628119,
            price_now, price_ago,
            4677792160494647834844974, True)

    expect = False
    actual = market.dataIsValid(data)
    assert expect == actual

    # check data is valid when price is just below the upper limit
    pow = Decimal(drift) * Decimal(3000) * Decimal(1-tol)
    price_now = int(price_ago * exp(pow))
    data = (1643583611, 600, 3000, 2569091057405103628119,
            price_now, price_ago,
            4677792160494647834844974, True)

    expect = True
    actual = market.dataIsValid(data)
    assert expect == actual


def test_data_is_valid_when_price_now_is_zero(market):
    data = (1643583611, 600, 3000, 2569091057405103628119,
            0, 2565497026032266989873,
            4677792160494647834844974, True)
    expect = False
    actual = market.dataIsValid(data)
    assert expect == actual


def test_data_is_valid_when_price_ago_is_zero(market):
    data = (1643583611, 600, 3000, 2569091057405103628119,
            2565497026032266989873, 0,
            4677792160494647834844974, True)
    expect = False
    actual = market.dataIsValid(data)
    assert expect == actual
