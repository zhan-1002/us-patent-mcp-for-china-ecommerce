"""
Unit tests for patent number format conversion and normalisation.

Tests the pure functions in:
- patent_mcp_server.google.gp_client (Google ↔ plain ↔ PPUBS format conversion)
- patent_mcp_server.util.validation (validate_google_pn)
- patent_mcp_server.patents (_normalize_pn, _is_design_patent, citation extraction)

No network access required — all tests are pure logic tests.
"""

import pytest

# ---------------------------------------------------------------------------
# Google Patents client format helpers
# ---------------------------------------------------------------------------

from patent_mcp_server.google.gp_client import (
    google_to_plain,
    plain_to_google,
    ppubs_to_plain,
    plain_to_ppubs,
    _is_design_plain,
)


class TestGoogleToPlain:
    """google_to_plain: Google format → plain patent number."""

    def test_design_patent_with_kind_code(self):
        assert google_to_plain("USD1066113S1") == "D1066113"

    def test_design_patent_without_kind_code(self):
        assert google_to_plain("USD1066113") == "D1066113"

    def test_utility_patent_with_kind_code(self):
        assert google_to_plain("US12345678B2") == "12345678"

    def test_utility_patent_with_a1(self):
        assert google_to_plain("US10000000A1") == "10000000"

    def test_already_plain_design(self):
        assert google_to_plain("D656429") == "D656429"

    def test_already_plain_utility(self):
        assert google_to_plain("7123456") == "7123456"

    def test_strips_whitespace(self):
        assert google_to_plain("  USD786128S1  ") == "D786128"

    def test_strips_us_prefix_from_nonstandard(self):
        """Non-standard format starting with US but not matching regex."""
        assert google_to_plain("USD786128") == "D786128"


class TestPlainToGoogle:
    """plain_to_google: plain → Google format."""

    def test_design_default_kind_s1(self):
        assert plain_to_google("D1066113") == "USD1066113S1"

    def test_utility_default_kind_b2(self):
        assert plain_to_google("12345678") == "US12345678B2"

    def test_explicit_kind(self):
        assert plain_to_google("D786128", kind="S") == "USD786128S"

    def test_already_google_format(self):
        assert plain_to_google("USD656429S1") == "USD656429S1"

    def test_strips_whitespace(self):
        assert plain_to_google("  D1050666  ") == "USD1050666S1"


class TestPpubsToPlain:
    """ppubs_to_plain: PPUBS format → plain."""

    def test_design_patent(self):
        assert ppubs_to_plain("US D1066113 S") == "D1066113"

    def test_utility_patent(self):
        assert ppubs_to_plain("US 12345678 S") == "12345678"

    def test_already_plain_passthrough(self):
        assert ppubs_to_plain("D656429") == "D656429"

    def test_strips_whitespace(self):
        assert ppubs_to_plain("  US D786128 S  ") == "D786128"


class TestPlainToPpubs:
    """plain_to_ppubs: plain → PPUBS format."""

    def test_design_patent(self):
        assert plain_to_ppubs("D1066113") == "US D1066113 S"

    def test_utility_patent(self):
        assert plain_to_ppubs("12345678") == "US 12345678 S"

    def test_already_ppubs_format(self):
        assert plain_to_ppubs("US D656429 S") == "US D656429 S"


class TestIsDesignPlain:
    """_is_design_plain: detect design vs utility by first character."""

    def test_design_starts_with_letter(self):
        assert _is_design_plain("D1066113") is True

    def test_design_starts_with_letter_other_format(self):
        assert _is_design_plain("D1066113S") is True

    def test_utility_starts_with_digit(self):
        assert _is_design_plain("12345678") is False

    def test_empty_string(self):
        assert _is_design_plain("") is False

    def test_whitespace_only(self):
        """Whitespace-only string — strip makes it empty, first char access may fail."""
        # Implementation uses pn[0].isalpha() after strip — whitespace-only
        # becomes "" after strip, so accessing pn[0] would raise IndexError.
        # This documents the behaviour; fix upstream if needed.
        with pytest.raises(IndexError):
            _is_design_plain("   ")


# ---------------------------------------------------------------------------
# validate_google_pn (validation module)
# ---------------------------------------------------------------------------

from patent_mcp_server.util.validation import validate_google_pn


class TestValidateGooglePn:
    """validate_google_pn: accept-and-normalise for Google Patents queries."""

    def test_google_format_design(self):
        assert validate_google_pn("USD1066113S1") == "D1066113"

    def test_google_format_utility(self):
        assert validate_google_pn("US12345678B2") == "12345678"

    def test_ppubs_format_design(self):
        assert validate_google_pn("US D1066113 S") == "D1066113"

    def test_ppubs_format_utility(self):
        assert validate_google_pn("US 7123456 S") == "7123456"

    def test_plain_design(self):
        assert validate_google_pn("D656429") == "D656429"

    def test_plain_utility(self):
        assert validate_google_pn("7123456") == "7123456"

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_google_pn("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_google_pn("   ")

    def test_garbage_raises(self):
        with pytest.raises(ValueError, match="Unrecognized patent number format"):
            validate_google_pn("not-a-patent-number")


# ---------------------------------------------------------------------------
# _normalize_pn (patents.py) — handles ALL 5 input formats
# ---------------------------------------------------------------------------

# Import may fail if mcp is not installed, but the test suite runs via uv
# which resolves all dependencies.
try:
    from patent_mcp_server.patents import _normalize_pn, _is_design_patent
    HAVE_PATENTS = True
except ImportError:
    HAVE_PATENTS = False


@pytest.mark.skipif(not HAVE_PATENTS, reason="patents module unavailable (mcp package not installed?)")
class TestNormalizePn:
    """_normalize_pn: any format → plain patent number."""

    # ── PPUBS format ───────────────────────────────────────────────

    def test_ppubs_design(self):
        assert _normalize_pn("US D786128 S") == "D786128"

    def test_ppubs_utility(self):
        assert _normalize_pn("US 12345678 S") == "12345678"

    # ── Google format ──────────────────────────────────────────────

    def test_google_design(self):
        assert _normalize_pn("USD1066113S1") == "D1066113"

    def test_google_utility(self):
        assert _normalize_pn("US10000000B2") == "10000000"

    # ── Plain with kind code ──────────────────────────────────────

    def test_plain_with_kind_code_design(self):
        assert _normalize_pn("D1066113S") == "D1066113"

    def test_plain_with_kind_code_utility(self):
        assert _normalize_pn("12345678B2") == "12345678"

    # ── Bare design (no kind code) ─────────────────────────────────

    def test_bare_design(self):
        assert _normalize_pn("D1050666") == "D1050666"

    # ── Bare utility (just digits) ─────────────────────────────────

    def test_bare_utility(self):
        assert _normalize_pn("7123456") == "7123456"

    # ── Edge cases ─────────────────────────────────────────────────

    def test_empty_string_returns_empty(self):
        assert _normalize_pn("") == ""

    def test_whitespace_only_returns_empty(self):
        assert _normalize_pn("   ") == ""

    def test_unrecognized_returns_empty(self):
        assert _normalize_pn("not-a-patent") == ""

    def test_normalized_equality_same_patent(self):
        """Two representations of the same patent should normalise equally."""
        assert _normalize_pn("USD656429S1") == _normalize_pn("US D656429 S") == "D656429"

    def test_normalized_equality_design_vs_utility(self):
        """Different patent types should not collide."""
        assert _normalize_pn("US12345678B2") != _normalize_pn("USD1234567S1")


@pytest.mark.skipif(not HAVE_PATENTS, reason="patents module unavailable")
class TestIsDesignPatent:
    """_is_design_patent: design vs utility detection."""

    def test_design_d_prefix(self):
        assert _is_design_patent("D656429") is True

    def test_design_d_prefix_in_google_format(self):
        assert _is_design_patent("USD1066113S1") is True

    def test_utility_no_d(self):
        assert _is_design_patent("12345678") is False

    def test_utility_us_prefix_no_d(self):
        assert _is_design_patent("US12345678B2") is False

    def test_empty_false(self):
        assert _is_design_patent("") is False

    def test_none_false(self):
        assert _is_design_patent(None) is False  # type: ignore


# ---------------------------------------------------------------------------
# Citation extraction helpers (patents.py)
# ---------------------------------------------------------------------------

try:
    from patent_mcp_server.patents import (
        _extract_pns_from_fields,
        _extract_backward_citation_pns,
        _extract_forward_citation_pns,
        _extract_citation_field_names,
        _BACKWARD_CITATION_FIELDS,
        _FORWARD_CITATION_FIELDS,
    )
    HAVE_CITATION = True
except ImportError:
    HAVE_CITATION = False


@pytest.mark.skipif(not HAVE_CITATION, reason="patents module unavailable")
class TestExtractPnsFromFields:
    """_extract_pns_from_fields: extract patent numbers from document fields."""

    def test_list_of_strings(self):
        doc = {"urpn": ["D656429", "D786128", "12345678"]}
        result = _extract_pns_from_fields(doc, ["urpn"])
        assert result == ["12345678", "D656429", "D786128"]  # sorted

    def test_list_of_dicts(self):
        doc = {
            "urpn": [
                {"patentNumber": "D656429"},
                {"documentId": "D786128"},
                {"number": "12345678"},
            ]
        }
        result = _extract_pns_from_fields(doc, ["urpn"])
        assert "D656429" in result
        assert "D786128" in result
        assert "12345678" in result

    def test_single_string_value(self):
        doc = {"usCitation": "D656429"}
        result = _extract_pns_from_fields(doc, ["usCitation"])
        assert result == ["D656429"]

    def test_multiple_fields(self):
        doc = {
            "urpn": ["D656429"],
            "usCitation": ["D786128"],
        }
        result = _extract_pns_from_fields(doc, ["urpn", "usCitation"])
        assert "D656429" in result
        assert "D786128" in result

    def test_deduplication(self):
        doc = {
            "urpn": ["D656429", "D656429"],
            "usCitation": ["D656429"],
        }
        result = _extract_pns_from_fields(doc, ["urpn", "usCitation"])
        assert result == ["D656429"]

    def test_empty_doc(self):
        result = _extract_pns_from_fields({}, ["urpn"])
        assert result == []

    def test_missing_field(self):
        result = _extract_pns_from_fields({"other": "data"}, ["urpn"])
        assert result == []


@pytest.mark.skipif(not HAVE_CITATION, reason="patents module unavailable")
class TestCitationDirectionSeparation:
    """Backward and forward citation extraction use distinct field groups."""

    def test_backward_uses_backward_fields(self):
        doc = {
            "urpn": ["D100000"],
            "forwardCitations": ["D200000"],
            "citingPatents": ["D300000"],
        }
        result = _extract_backward_citation_pns(doc)
        # Only backward fields are checked — forwardCitations/citingPatents
        # should NOT appear in backward results.
        assert "D100000" in result
        assert "D200000" not in result
        assert "D300000" not in result

    def test_forward_uses_forward_fields(self):
        doc = {
            "urpn": ["D100000"],
            "forwardCitations": ["D200000"],
            "citingPatents": ["D300000"],
        }
        result = _extract_forward_citation_pns(doc)
        # Only forward fields are checked — urpn/usCitation should NOT appear.
        assert "D200000" in result
        assert "D300000" in result
        assert "D100000" not in result

    def test_backward_and_forward_disjoint(self):
        """Ensure no field name appears in both groups (would cause direction confusion)."""
        backward = set(_BACKWARD_CITATION_FIELDS)
        forward = set(_FORWARD_CITATION_FIELDS)
        assert backward.isdisjoint(forward), (
            f"Overlap detected! Shared fields: {backward & forward}"
        )


@pytest.mark.skipif(not HAVE_CITATION, reason="patents module unavailable")
class TestExtractCitationFieldNames:
    """_extract_citation_field_names: discover which citation fields are present."""

    def test_present_fields(self):
        doc = {"urpn": ["D656429"], "forwardCitations": ["D786128"], "other": "x"}
        names = _extract_citation_field_names(doc)
        assert "urpn" in names
        assert "forwardCitations" in names
        assert "other" not in names  # not a citation field

    def test_empty_fields_excluded(self):
        """Empty-list / falsy values should not be reported as present."""
        doc = {"urpn": [], "forwardCitations": None}
        names = _extract_citation_field_names(doc)
        assert "urpn" not in names
        assert "forwardCitations" not in names
