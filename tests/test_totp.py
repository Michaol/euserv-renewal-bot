"""
Tests for HOTP/TOTP functions.
Validates that our HOTP implementation produces consistent results.
"""
import pytest
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from Euserv_Renewal import _hotp as hotp


class TestHOTP:
    """
    Test cases for hotp() function.
    Uses a test key to verify consistent output.
    """

    # Test key (Base32 encoded)
    TEST_KEY = "GEZDGNBVGY3TQOJQ"

    def test_output_is_6_digits(self):
        """Test that output is always 6 digits."""
        for i in range(20):
            result = hotp(self.TEST_KEY, i)
            assert len(result) == 6, f"Counter {i}: expected 6 digits, got {len(result)}"
            assert result.isdigit(), f"Counter {i}: expected digits only, got {result}"

    def test_consistency(self):
        """Test that same inputs produce same outputs."""
        for i in range(10):
            result1 = hotp(self.TEST_KEY, i)
            result2 = hotp(self.TEST_KEY, i)
            assert result1 == result2, f"Counter {i}: inconsistent results"

    def test_different_counters_different_results(self):
        """Test that different counters produce different results (mostly)."""
        results = [hotp(self.TEST_KEY, i) for i in range(100)]
        # At least 90% should be unique (allowing for some collisions)
        unique_count = len(set(results))
        assert unique_count >= 90, f"Expected at least 90 unique results, got {unique_count}"

    def test_different_keys_different_results(self):
        """Test that different keys produce different results."""
        key1 = "GEZDGNBVGY3TQOJQ"
        key2 = "JBSWY3DPEHPK3PXP"
        result1 = hotp(key1, 0)
        result2 = hotp(key2, 0)
        assert result1 != result2, "Different keys should produce different results"

    def test_lowercase_key(self):
        """Test that lowercase keys work (should be converted to uppercase)."""
        result_upper = hotp("GEZDGNBVGY3TQOJQ", 0)
        result_lower = hotp("gezdgnbvgy3tqojq", 0)
        assert result_upper == result_lower, "Case should not affect result"


class TestValidateConfig:
    """Test cases for RenewalBot.validate_config() method."""

    def test_validate_config_import(self):
        """Test that RenewalBot has validate_config method."""
        from Euserv_Renewal import RenewalBot
        bot = RenewalBot()
        assert callable(bot.validate_config)

    def test_validate_config_returns_tuple(self):
        """Test that validate_config returns a tuple."""
        from Euserv_Renewal import RenewalBot
        bot = RenewalBot()
        result = bot.validate_config()
        assert isinstance(result, tuple)
        assert len(result) == 2

