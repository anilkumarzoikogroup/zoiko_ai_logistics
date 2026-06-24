"""RFC 8785 JCS test vectors -- CI hard block (must be 100% green).

All tests marked `jcs_vector` run via `make test-vectors` and block CI merge.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from zoiko_common.crypto.jcs import canonicalize


def _jcs(data: object) -> str:
    return canonicalize(data).decode("utf-8")


def _jcs_parse(raw_json: str) -> str:
    return _jcs(json.loads(raw_json))


@pytest.mark.jcs_vector
class TestKeyOrdering:
    def test_simple_two_keys(self):
        assert _jcs({"z": 1, "a": 2}) == '{"a":2,"z":1}'

    def test_empty_object(self):
        assert _jcs({}) == "{}"

    def test_single_key(self):
        assert _jcs({"key": "value"}) == '{"key":"value"}'

    def test_unicode_key_ordering(self):
        assert _jcs({"€": 2, "$": 1}) == '{"$":1,"€":2}'

    def test_nested_objects_sorted(self):
        assert _jcs({"z": {"b": 1, "a": 2}, "a": 3}) == '{"a":3,"z":{"a":2,"b":1}}'

    def test_array_preserves_order(self):
        assert _jcs([3, 1, 2]) == "[3,1,2]"

    def test_empty_array(self):
        assert _jcs([]) == "[]"


@pytest.mark.jcs_vector
class TestNumbers:
    def test_integer(self):
        assert _jcs(1) == "1"

    def test_negative_integer(self):
        assert _jcs(-42) == "-42"

    def test_zero(self):
        assert _jcs(0) == "0"

    def test_negative_zero_float(self):
        assert _jcs(-0.0) == "0"

    def test_float_strip_trailing_zero(self):
        assert _jcs_parse("4.50") == "4.5"

    def test_float_integer_valued(self):
        assert _jcs_parse("1.0") == "1"

    def test_large_exponent(self):
        assert _jcs_parse("1e30") == "1e+30"

    def test_small_decimal(self):
        assert _jcs_parse("2e-3") == "0.002"

    def test_small_decimal_trailing_zeros(self):
        assert _jcs_parse("0.000990") == "0.00099"

    def test_float_roundtrip(self):
        assert _jcs_parse("333333333.33333329") == "333333333.3333333"

    def test_large_float_exponent(self):
        assert _jcs_parse("1.5e+24") == "1.5e+24"

    def test_bool_true(self):
        assert _jcs(True) == "true"

    def test_bool_false(self):
        assert _jcs(False) == "false"

    def test_null(self):
        assert _jcs(None) == "null"


@pytest.mark.jcs_vector
class TestStringEscaping:
    def test_plain_ascii(self):
        assert _jcs("hello") == '"hello"'

    def test_escape_backslash(self):
        assert _jcs("a\\b") == '"a\\\\b"'

    def test_escape_double_quote(self):
        assert _jcs('say "hi"') == '"say \\"hi\\""'

    def test_escape_tab(self):
        assert _jcs("\t") == '"\\t"'

    def test_escape_newline(self):
        assert _jcs("\n") == '"\\n"'

    def test_escape_carriage_return(self):
        assert _jcs("\r") == '"\\r"'

    def test_escape_backspace(self):
        assert _jcs("\x08") == '"\\b"'

    def test_escape_formfeed(self):
        assert _jcs("\x0c") == '"\\f"'

    def test_escape_null_byte(self):
        assert _jcs("\x00") == '"\\u0000"'

    def test_escape_del(self):
        assert _jcs("\x7f") == '"\\u007f"'

    def test_escape_c1_nel(self):
        assert _jcs("\x85") == '"\\u0085"'

    def test_escape_c0_si(self):
        assert _jcs("\x0f") == '"\\u000f"'

    def test_unicode_euro_literal(self):
        assert _jcs("€") == '"€"'

    def test_unicode_j_caron_literal(self):
        assert _jcs("ǰ") == '"ǰ"'

    def test_solidus_not_escaped(self):
        assert _jcs("a/b") == '"a/b"'


def _build_b1_string() -> str:
    return (
        "€"  # euro sign
        "\x24"    # $
        "\x0f"    # SI control (C0)
        "\n"      # LF  (U+000A)
        "AZ!"
        "\x85"    # NEL (C1)
        "\t"      # HT  (U+0009)
        "'"       # apostrophe
        "ǰ"  # j with caron
        " "       # space
        "\x00"    # null
        "\x7f"    # DEL
    )


def _build_b1_input() -> dict:
    return {
        "numbers": [333333333.33333329, 1e30, 4.50, 2e-3, 0.000990, 1.0, 1.5e24],
        "string": _build_b1_string(),
        "literals": [None, True, False],
    }


_B1_EXPECTED = (
    '{"literals":[null,true,false],'
    '"numbers":[333333333.3333333,1e+30,4.5,0.002,0.00099,1,1.5e+24],'
    '"string":"€$\\u000f\\nAZ!\\u0085\\t\'ǰ \\u0000\\u007f"}'
)


@pytest.mark.jcs_vector
def test_rfc8785_appendix_b1_structure():
    result = canonicalize(_build_b1_input()).decode("utf-8")
    assert result.startswith('{"literals":[null,true,false],"numbers":')
    assert '"numbers":[333333333.3333333,1e+30,4.5,0.002,0.00099,1,1.5e+24]' in result
    assert '"string":"€$\\u000f\\nAZ!\\u0085\\t\'ǰ \\u0000\\u007f"' in result


@pytest.mark.jcs_vector
def test_rfc8785_appendix_b1_full_canonical():
    result = canonicalize(_build_b1_input()).decode("utf-8")
    assert result == _B1_EXPECTED, f"\nExpected: {_B1_EXPECTED!r}\n     Got: {result!r}"


@pytest.mark.jcs_vector
def test_rfc8785_appendix_b1_sha256():
    """SHA-256 of canonical bytes must be stable. Failure means JCS is wrong."""
    canonical = canonicalize(_build_b1_input())
    digest = hashlib.sha256(canonical).hexdigest()
    expected_digest = hashlib.sha256(_B1_EXPECTED.encode("utf-8")).hexdigest()
    assert digest == expected_digest, (
        "JCS SHA-256 mismatch!\n"
        f"  got:      {digest}\n"
        f"  expected: {expected_digest}\n"
        f"  canonical: {canonical!r}"
    )


@pytest.mark.jcs_vector
def test_canonicalize_is_idempotent():
    data = {"b": [1, 2, 3], "a": {"y": None, "x": True}}
    first = canonicalize(data)
    second = canonicalize(json.loads(first.decode("utf-8")))
    assert first == second


@pytest.mark.jcs_vector
def test_canonicalize_returns_bytes():
    assert isinstance(canonicalize({}), bytes)


def test_non_finite_float_raises():
    with pytest.raises(ValueError, match="non-finite"):
        canonicalize(float("inf"))


def test_unsupported_type_raises():
    with pytest.raises(TypeError, match="unsupported type"):
        canonicalize(object())  # type: ignore[arg-type]