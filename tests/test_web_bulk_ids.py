from web import _parse_bulk_order_ids


def test_parse_bulk_order_ids_supports_commas_spaces_newlines():
    raw = "1001S, 1002S\n1003S   1004S,\n\n1005S"
    assert _parse_bulk_order_ids(raw) == ["1001S", "1002S", "1003S", "1004S", "1005S"]


def test_parse_bulk_order_ids_empty_input():
    assert _parse_bulk_order_ids("") == []
    assert _parse_bulk_order_ids("   ,  \n") == []
