import aiowamp


def test_bwlist():
    bwlist = aiowamp.BlackWhiteList(excluded_ids=[7891255, 1245751])
    assert 5555 in bwlist
    assert 7891255 not in bwlist
    assert 1245751 not in bwlist

    bwlist = aiowamp.BlackWhiteList(eligible_ids=[7891255, 1245751, 9912315],
                                    excluded_ids=[7891255])
    assert 1245751 in bwlist
    assert 9912315 in bwlist
    assert 7891255 not in bwlist
    assert 5555 not in bwlist
