# Test suite for Euserv Renewal Bot
import pytest
import email
from email.mime.text import MIMEText
from unittest.mock import Mock, patch, MagicMock

# Import the module under test
from Euserv_Renewal import (
    RenewalBot, LogLevel, _safe_eval_math, _totp, _hotp,
    CaptchaError, LoginError, RenewalError, PinRetrievalError,
    EXIT_SUCCESS, EXIT_FAILURE, EXIT_SKIPPED,
    CAPTCHA_PROMPT, TWO_FA_PROMPT, LOGIN_SUCCESS_INDICATORS,
    EUSERV_BASE_URL, EUSERV_CAPTCHA_URL, TRUECAPTCHA_API_URL
)


class TestSafeEvalMath:
    """Test _safe_eval_math utility function"""
    
    def test_addition(self):
        assert _safe_eval_math('3+5') == 8
        assert _safe_eval_math('10+20') == 30
    
    def test_subtraction(self):
        assert _safe_eval_math('10-3') == 7
        assert _safe_eval_math('100-50') == 50
    
    def test_multiplication(self):
        assert _safe_eval_math('4*2') == 8
        assert _safe_eval_math('7*8') == 56
    
    def test_division(self):
        assert _safe_eval_math('10/2') == 5
        assert _safe_eval_math('15/3') == 5
    
    def test_complex_expression(self):
        assert _safe_eval_math('3+5*2') == 13
        assert _safe_eval_math('10-2*3') == 4
    
    def test_invalid_expression(self):
        assert _safe_eval_math('invalid') is None
        assert _safe_eval_math('abc') is None
        assert _safe_eval_math('') is None
    
    def test_division_by_zero(self):
        assert _safe_eval_math('10/0') is None


class TestRenewalBotInit:
    """Test RenewalBot initialization"""
    
    def test_init_default_values(self):
        bot = RenewalBot()
        assert bot.log_messages == []
        assert bot.current_login_attempt == 1
        assert bot.session is None
        assert bot.sess_id is None
        assert bot._ocr is None
    
    def test_log_method(self):
        bot = RenewalBot()
        bot.log("Test message")
        assert len(bot.log_messages) == 1
        assert "Test message" in bot.log_messages[0]
    
    def test_log_with_level(self):
        bot = RenewalBot()
        bot.log("Success!", LogLevel.SUCCESS)
        assert "✅" in bot.log_messages[0]
        
        bot.log("Error!", LogLevel.ERROR)
        assert "❌" in bot.log_messages[1]


class TestIsLoginSuccess:
    """Test _is_login_success static method"""
    
    def test_success_with_hello(self):
        assert RenewalBot._is_login_success("Hello, user!") is True
    
    def test_success_with_confirm(self):
        assert RenewalBot._is_login_success("Confirm or change your customer data here") is True
    
    def test_failure_no_indicators(self):
        assert RenewalBot._is_login_success("Login failed") is False
        assert RenewalBot._is_login_success("Error occurred") is False
    
    def test_empty_string(self):
        assert RenewalBot._is_login_success("") is False


class TestExtractEmailBody:
    """Test _extract_email_body static method"""
    
    def test_simple_text_email(self):
        msg = MIMEText("Hello, this is a test email body.", 'plain', 'utf-8')
        body = RenewalBot._extract_email_body(msg)
        assert "Hello" in body
        assert "test email body" in body
    
    def test_empty_body(self):
        msg = MIMEText("", 'plain', 'utf-8')
        body = RenewalBot._extract_email_body(msg)
        assert body == ""


class TestValidateConfig:
    """Test validate_config method"""
    
    @patch.dict('os.environ', {}, clear=True)
    def test_all_missing(self):
        # Re-import to get fresh env vars
        bot = RenewalBot()
        _, _ = bot.validate_config()
        # Note: This test depends on the actual env var state
        # In real testing, we'd mock the module-level variables
    
    def test_returns_tuple(self):
        bot = RenewalBot()
        result = bot.validate_config()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], list)


class TestCleanup:
    """Test _cleanup method"""
    
    def test_cleanup_with_session(self):
        bot = RenewalBot()
        mock_session = Mock()
        bot.session = mock_session
        bot._cleanup()
        mock_session.close.assert_called_once()
        assert bot.session is None
    
    def test_cleanup_without_session(self):
        bot = RenewalBot()
        bot.session = None
        # Should not raise
        bot._cleanup()
        assert bot.session is None


class TestConstants:
    """Test that constants are properly defined"""
    
    def test_exit_codes(self):
        assert EXIT_SUCCESS == 0
        assert EXIT_FAILURE == 1
        assert EXIT_SKIPPED == 2
    
    def test_urls(self):
        assert "euserv.com" in EUSERV_BASE_URL
        assert "euserv.com" in EUSERV_CAPTCHA_URL
        assert "apitruecaptcha.org" in TRUECAPTCHA_API_URL
    
    def test_prompts(self):
        assert "captcha" in CAPTCHA_PROMPT.lower()
        assert "PIN" in TWO_FA_PROMPT
    
    def test_login_indicators(self):
        assert "Hello" in LOGIN_SUCCESS_INDICATORS
        assert len(LOGIN_SUCCESS_INDICATORS) >= 2


class TestPrewarmOcr:
    """Test prewarm_ocr method"""
    
    def test_prewarm_ocr_exists(self):
        bot = RenewalBot()
        assert hasattr(bot, 'prewarm_ocr')
        assert callable(bot.prewarm_ocr)


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
