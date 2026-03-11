"""
Tests for utils/validation.py

Covers: SSRF prevention, URL validation, competitor name validation.
"""

import pytest
from utils.validation import validate_url, validate_competitor_name, is_private_ip


class TestValidateUrl:
    """Tests for URL validation / SSRF prevention."""

    def test_valid_https_url(self):
        is_valid, _ = validate_url("https://example.com/page")
        assert is_valid

    def test_valid_http_url(self):
        is_valid, _ = validate_url("http://example.com")
        assert is_valid

    def test_rejects_localhost(self):
        is_valid, error = validate_url("http://localhost:8080/admin")
        assert not is_valid
        assert "localhost" in error.lower() or "blocked" in error.lower()

    def test_rejects_127_0_0_1(self):
        is_valid, _ = validate_url("http://127.0.0.1:3000")
        assert not is_valid

    def test_rejects_private_ip_10(self):
        is_valid, _ = validate_url("http://10.0.0.1/internal")
        assert not is_valid

    def test_rejects_private_ip_192(self):
        is_valid, _ = validate_url("http://192.168.1.1")
        assert not is_valid

    def test_rejects_private_ip_172(self):
        is_valid, _ = validate_url("http://172.16.0.1")
        assert not is_valid

    def test_rejects_ftp_scheme(self):
        is_valid, error = validate_url("ftp://files.example.com")
        assert not is_valid
        assert "scheme" in error.lower()

    def test_rejects_file_scheme(self):
        is_valid, _ = validate_url("file:///etc/passwd")
        assert not is_valid

    def test_rejects_empty_url(self):
        is_valid, _ = validate_url("")
        assert not is_valid

    def test_rejects_none_like_empty(self):
        is_valid, _ = validate_url("   ")
        assert not is_valid

    def test_rejects_no_hostname(self):
        is_valid, _ = validate_url("https://")
        assert not is_valid


class TestIsPrivateIp:
    """Tests for private IP detection."""

    def test_loopback(self):
        assert is_private_ip("127.0.0.1") is True

    def test_class_a_private(self):
        assert is_private_ip("10.255.255.1") is True

    def test_public_ip(self):
        assert is_private_ip("8.8.8.8") is False

    def test_hostname_not_ip(self):
        """Hostnames (not IPs) should return False (not private)."""
        assert is_private_ip("example.com") is False


class TestValidateCompetitorName:
    """Tests for competitor name validation."""

    def test_valid_name(self):
        is_valid, _ = validate_competitor_name("CrowdStrike")
        assert is_valid

    def test_valid_name_with_spaces(self):
        is_valid, _ = validate_competitor_name("Palo Alto Networks")
        assert is_valid

    def test_valid_name_with_ampersand(self):
        is_valid, _ = validate_competitor_name("AT&T")
        assert is_valid

    def test_rejects_sql_injection(self):
        is_valid, _ = validate_competitor_name("test'; DROP TABLE scans;--")
        assert not is_valid

    def test_rejects_path_traversal(self):
        is_valid, _ = validate_competitor_name("../../etc/passwd")
        assert not is_valid

    def test_rejects_empty(self):
        is_valid, _ = validate_competitor_name("")
        assert not is_valid

    def test_rejects_too_long(self):
        is_valid, _ = validate_competitor_name("A" * 101)
        assert not is_valid
