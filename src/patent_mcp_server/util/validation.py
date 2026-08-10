"""
Input validation models for USPTO Patent MCP Server.

This module provides Pydantic models for validating input parameters
to ensure data integrity and provide clear error messages.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional


class PatentNumberInput(BaseModel):
    """Validation model for patent numbers."""

    patent_number: str = Field(..., min_length=1, description="Patent number")

    @field_validator('patent_number')
    @classmethod
    def validate_patent_number(cls, v: str) -> str:
        """Validate and clean patent number.

        Preserves design/plant/reissue prefixes (D, PP, RE) while stripping
        country codes (US), kind codes (B2, S1, A1), and formatting characters.

        Accepts: D1066113, D1066113S, USD1066113S1, US D1066113 S,
                 12345678, 12345678B2, US12345678B2, US 12345678 S.
        """
        import re

        pn = str(v).strip().upper()
        if not pn:
            raise ValueError("Patent number cannot be empty")

        # US + optional space + body with optional letter prefix + optional kind code
        # e.g. US D1066113 S, USD1066113S1, US12345678B2, US 12345678 S
        m = re.match(r'^US\s*([A-Z]{0,2}\d+)(?:\s*[A-Z]\d*)?$', pn)
        if m:
            result = m.group(1)
            if result and any(c.isdigit() for c in result):
                return result

        # Body with optional letter prefix + optional kind code
        # e.g. D1066113S, 12345678B2, D1066113, 12345678, PP12345
        m = re.match(r'^([A-Z]{0,2}\d+)(?:\s*[A-Z]\d*)?$', pn)
        if m:
            result = m.group(1)
            if result and any(c.isdigit() for c in result):
                return result

        raise ValueError(
            f"Unrecognized patent number format: {v!r}. "
            f"Expected formats: 'D1066113', 'USD1066113S1', "
            f"'US D1066113 S', '12345678', or 'US12345678B2'."
        )


class ApplicationNumberInput(BaseModel):
    """Validation model for application numbers."""

    app_num: str = Field(..., min_length=1, description="Application number")

    @field_validator('app_num')
    @classmethod
    def validate_app_num(cls, v: str) -> str:
        """Validate and clean application number."""
        # Remove slashes, commas, and spaces
        cleaned = ''.join(c for c in str(v) if c.isdigit())
        if not cleaned:
            raise ValueError("Application number must contain at least one digit")
        if len(cleaned) < 6:
            raise ValueError("Application number must be at least 6 digits")
        return cleaned


class SearchQueryInput(BaseModel):
    """Validation model for search queries."""

    query: str = Field(..., min_length=1, description="Search query string")
    start: int = Field(default=0, ge=0, description="Starting position")
    limit: int = Field(default=100, ge=1, le=1000, description="Maximum results")

    @field_validator('query')
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Validate query string."""
        v = v.strip()
        if not v:
            raise ValueError("Query cannot be empty or whitespace only")
        return v


class GuidInput(BaseModel):
    """Validation model for document GUIDs."""

    guid: str = Field(..., min_length=1, description="Document GUID")
    source_type: str = Field(..., min_length=1, description="Source type")

    @field_validator('guid')
    @classmethod
    def validate_guid(cls, v: str) -> str:
        """Validate GUID format."""
        v = v.strip()
        if not v:
            raise ValueError("GUID cannot be empty")
        return v

    @field_validator('source_type')
    @classmethod
    def validate_source_type(cls, v: str) -> str:
        """Validate source type."""
        v = v.strip()
        valid_sources = ["USPAT", "US-PGPUB", "USOCR"]
        if v not in valid_sources:
            raise ValueError(f"Source type must be one of: {', '.join(valid_sources)}")
        return v


class PaginationInput(BaseModel):
    """Validation model for pagination parameters."""

    offset: int = Field(default=0, ge=0, description="Number of records to skip")
    limit: int = Field(default=25, ge=1, le=1000, description="Number of records to return")


def validate_patent_number(patent_number: str) -> str:
    """
    Validate and clean a patent number.

    Args:
        patent_number: Raw patent number input

    Returns:
        Cleaned patent number string

    Raises:
        ValueError: If patent number is invalid
    """
    try:
        validated = PatentNumberInput(patent_number=patent_number)
        return validated.patent_number
    except Exception as e:
        raise ValueError(f"Invalid patent number: {str(e)}")


def validate_app_number(app_num: str) -> str:
    """
    Validate and clean an application number.

    Args:
        app_num: Raw application number input

    Returns:
        Cleaned application number string

    Raises:
        ValueError: If application number is invalid
    """
    try:
        validated = ApplicationNumberInput(app_num=app_num)
        return validated.app_num
    except Exception as e:
        raise ValueError(f"Invalid application number: {str(e)}")


def validate_google_pn(patent_number: str) -> str:
    """Validate and normalize a patent number for Google Patents queries.

    Accepts any common format (Google, PPUBS, or plain) and returns the
    plain form (e.g. ``"D1066113"``).

    Args:
        patent_number: Patent number in any format:
            - Google: ``"USD1066113S1"``
            - PPUBS:  ``"US D1066113 S"``
            - Plain:  ``"D1066113"``

    Returns:
        Plain patent number (e.g. ``"D1066113"``).

    Raises:
        ValueError: If the patent number doesn't match any known format.
    """
    import re

    pn = str(patent_number).strip()
    if not pn:
        raise ValueError("Patent number cannot be empty")

    # Already plain: D + digits (design) or just digits (utility)
    if re.match(r"^[A-Z]\d+$", pn):
        return pn
    if re.match(r"^\d+$", pn):
        return pn

    # Google format: USD1066113S1 (design) or US12345678B2 (utility)
    # Body may start with a letter (design) or be purely numeric (utility).
    m = re.match(r"^US([A-Z]?\d+)[A-Z]\d*$", pn)
    if m:
        return m.group(1)

    # PPUBS format: US D1066113 S or US 12345678 S
    m = re.match(r"^US\s+([A-Z]?\d+)\s+[A-Z]\d*$", pn)
    if m:
        return m.group(1)

    raise ValueError(
        f"Unrecognized patent number format: {patent_number!r}. "
        f"Expected formats: 'D1066113', 'USD1066113S1', '12345678', 'US12345678B2', or 'US D1066113 S'."
    )
