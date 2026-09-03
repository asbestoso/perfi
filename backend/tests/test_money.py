from decimal import Decimal

from app.services.money import to_cents, to_dollars


def test_to_cents_dollars_string():
    assert to_cents("12.34") == 1234


def test_to_cents_negative():
    assert to_cents("-5") == -500


def test_to_cents_rounds_half_up():
    assert to_cents("12.345") == 1235
    assert to_cents("12.344") == 1234


def test_to_cents_accepts_float_and_decimal():
    assert to_cents(7.5) == 750
    assert to_cents(Decimal("3.21")) == 321


def test_to_dollars_negative_and_small():
    assert to_dollars(-1250) == "-12.50"
    assert to_dollars(5) == "0.05"
    assert to_dollars(0) == "0.00"


def test_cents_dollars_roundtrip():
    for cents in (-100001, -99, 0, 1, 2500):
        assert to_cents(to_dollars(cents)) == cents


def test_sanitizes_bank_formats():
    assert to_cents("$1,234.56") == 123456
    assert to_cents("(12.34)") == -1234
    assert to_cents("  $ 5.00 ") == 500
