from brownie import OverlayV1UniswapV3Factory, reverts


def test_deploy_factory_reverts_when_cardinality_lt_macro(alice, uni,
                                                          uni_factory):
    micro_window = 600
    macro_window = 3600
    avg_block_time = 14
    ovl = uni

    # check factory deploy reverts when cardinality too small given
    # micro and macro windows
    cardinality_min = 10
    with reverts("OVLV1: cardinality < macroWindow"):
        _ = alice.deploy(OverlayV1UniswapV3Factory, ovl, uni_factory,
                         micro_window, macro_window, cardinality_min,
                         avg_block_time)
