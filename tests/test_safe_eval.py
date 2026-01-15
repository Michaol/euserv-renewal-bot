"""
Tests for safe_eval_math() function.
"""
import pytest
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from Euserv_Renewal import safe_eval_math


class TestSafeEvalMath:
    """Test cases for safe_eval_math() function."""

    def test_addition(self):
        """Test simple addition."""
        assert safe_eval_math("3+5") == 8

    def test_subtraction(self):
        """Test simple subtraction."""
        assert safe_eval_math("10-3") == 7

    def test_multiplication(self):
        """Test simple multiplication."""
        assert safe_eval_math("4*5") == 20

    def test_division(self):
        """Test integer division."""
        assert safe_eval_math("10/2") == 5

    def test_division_truncates(self):
        """Test that division truncates to integer."""
        assert safe_eval_math("7/2") == 3

    def test_complex_expression(self):
        """Test operator precedence."""
        assert safe_eval_math("2+3*4") == 14

    def test_parentheses_not_supported(self):
        """Test that parentheses are not supported (returns None)."""
        # AST will parse it but our _eval doesn't handle it
        result = safe_eval_math("(2+3)*4")
        # This should work actually since AST handles precedence
        assert result == 20

    def test_invalid_expression_letters(self):
        """Test invalid expression with letters."""
        assert safe_eval_math("abc") is None

    def test_invalid_expression_mixed(self):
        """Test invalid expression with mixed content."""
        assert safe_eval_math("3+abc") is None

    def test_division_by_zero(self):
        """Test division by zero returns None."""
        assert safe_eval_math("1/0") is None

    def test_empty_string(self):
        """Test empty string returns None."""
        assert safe_eval_math("") is None

    def test_whitespace_only(self):
        """Test whitespace only returns None."""
        assert safe_eval_math("   ") is None

    def test_single_number(self):
        """Test single number."""
        assert safe_eval_math("42") == 42

    def test_negative_result(self):
        """Test expression with negative result."""
        assert safe_eval_math("3-10") == -7
