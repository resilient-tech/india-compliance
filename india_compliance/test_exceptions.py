"""
Unit tests for exceptions module.
"""

import unittest

from india_compliance.exceptions import (
    AlreadyGeneratedError,
    GSPLimitExceededError,
    GSPServerError,
    GatewayTimeoutError,
    InvalidAuthTokenError,
    InvalidOTPError,
    NotApplicableError,
    OTPRequestedError,
)


class TestGSPServerError(unittest.TestCase):
    """Test GSPServerError exception"""

    def test_gsp_server_error_default_message(self):
        """Test default error message"""
        error = GSPServerError("Test")
        self.assertEqual(error.message, "GSP/GST server is down")
        self.assertIsNotNone(error.title)

    def test_gsp_server_error_is_validation_error(self):
        """Test that GSPServerError is a proper exception"""
        error = GSPServerError("Test")
        self.assertIsInstance(error, Exception)

    def test_gsp_server_error_can_be_raised(self):
        """Test that error can be raised and caught"""
        with self.assertRaises(GSPServerError):
            raise GSPServerError("Test")


class TestGSPLimitExceededError(unittest.TestCase):
    """Test GSPLimitExceededError exception"""

    def test_gsp_limit_exceeded_error_message(self):
        """Test error message"""
        error = GSPLimitExceededError("Test")
        self.assertEqual(error.message, "GSP/GST account limit exceeded")

    def test_gsp_limit_exceeded_error_status_code(self):
        """Test HTTP status code"""
        error = GSPLimitExceededError("Test")
        self.assertEqual(error.http_status_code, 429)

    def test_gsp_limit_exceeded_is_gsp_server_error(self):
        """Test inheritance"""
        error = GSPLimitExceededError("Test")
        self.assertIsInstance(error, GSPServerError)

    def test_gsp_limit_exceeded_can_be_raised(self):
        """Test that error can be raised"""
        with self.assertRaises(GSPLimitExceededError):
            raise GSPLimitExceededError("Test")


class TestGatewayTimeoutError(unittest.TestCase):
    """Test GatewayTimeoutError exception"""

    def test_gateway_timeout_error_message(self):
        """Test error message"""
        error = GatewayTimeoutError("Test")
        self.assertEqual(error.message, "The server took too long to respond")

    def test_gateway_timeout_error_status_code(self):
        """Test HTTP status code"""
        error = GatewayTimeoutError("Test")
        self.assertEqual(error.http_status_code, 504)

    def test_gateway_timeout_is_gsp_server_error(self):
        """Test inheritance"""
        error = GatewayTimeoutError("Test")
        self.assertIsInstance(error, GSPServerError)

    def test_gateway_timeout_can_be_raised(self):
        """Test that error can be raised"""
        with self.assertRaises(GatewayTimeoutError):
            raise GatewayTimeoutError("Test")


class TestOTPRequestedError(unittest.TestCase):
    """Test OTPRequestedError exception"""

    def test_otp_requested_error_default_message(self):
        """Test default error message"""
        error = OTPRequestedError()
        self.assertIn("OTP has been requested", str(error))

    def test_otp_requested_error_custom_message(self):
        """Test custom error message"""
        error = OTPRequestedError("Custom message")
        self.assertIn("Custom message", str(error))

    def test_otp_requested_error_with_response(self):
        """Test error with response data"""
        response_data = {"status": "success"}
        error = OTPRequestedError(response=response_data)
        self.assertEqual(error.response, response_data)

    def test_otp_requested_error_response_none_by_default(self):
        """Test that response is None by default"""
        error = OTPRequestedError()
        self.assertIsNone(error.response)

    def test_otp_requested_error_can_be_raised(self):
        """Test that error can be raised"""
        with self.assertRaises(OTPRequestedError):
            raise OTPRequestedError()

    def test_otp_requested_error_preserves_response(self):
        """Test that response is accessible after raising"""
        response_data = {"request_id": "123"}
        try:
            raise OTPRequestedError(response=response_data)
        except OTPRequestedError as e:
            self.assertEqual(e.response, response_data)


class TestInvalidOTPError(unittest.TestCase):
    """Test InvalidOTPError exception"""

    def test_invalid_otp_error_default_message(self):
        """Test default error message"""
        error = InvalidOTPError()
        self.assertIn("Invalid OTP", str(error))

    def test_invalid_otp_error_custom_message(self):
        """Test custom error message"""
        error = InvalidOTPError("OTP mismatch")
        self.assertIn("OTP mismatch", str(error))

    def test_invalid_otp_error_with_response(self):
        """Test error with response data"""
        response_data = {"error": "Invalid OTP"}
        error = InvalidOTPError(response=response_data)
        self.assertEqual(error.response, response_data)

    def test_invalid_otp_error_response_none_by_default(self):
        """Test that response is None by default"""
        error = InvalidOTPError()
        self.assertIsNone(error.response)

    def test_invalid_otp_error_can_be_raised(self):
        """Test that error can be raised"""
        with self.assertRaises(InvalidOTPError):
            raise InvalidOTPError()

    def test_invalid_otp_error_preserves_response(self):
        """Test that response is accessible after raising"""
        response_data = {"retries_left": 2}
        try:
            raise InvalidOTPError(response=response_data)
        except InvalidOTPError as e:
            self.assertEqual(e.response, response_data)


class TestInvalidAuthTokenError(unittest.TestCase):
    """Test InvalidAuthTokenError exception"""

    def test_invalid_auth_token_error_default_message(self):
        """Test default error message"""
        error = InvalidAuthTokenError()
        self.assertIn("Invalid Auth Token", str(error))

    def test_invalid_auth_token_error_custom_message(self):
        """Test custom error message"""
        error = InvalidAuthTokenError("Token expired")
        self.assertIn("Token expired", str(error))

    def test_invalid_auth_token_error_can_be_raised(self):
        """Test that error can be raised"""
        with self.assertRaises(InvalidAuthTokenError):
            raise InvalidAuthTokenError()

    def test_invalid_auth_token_error_preserves_message(self):
        """Test that message is accessible after raising"""
        try:
            raise InvalidAuthTokenError("Token revoked")
        except InvalidAuthTokenError as e:
            self.assertIn("Token revoked", str(e))


class TestNotApplicableError(unittest.TestCase):
    """Test NotApplicableError exception"""

    def test_not_applicable_error_can_be_created(self):
        """Test that error can be created"""
        error = NotApplicableError("e-Invoice not applicable")
        self.assertIsInstance(error, Exception)

    def test_not_applicable_error_can_be_raised(self):
        """Test that error can be raised"""
        with self.assertRaises(NotApplicableError):
            raise NotApplicableError()

    def test_not_applicable_error_with_message(self):
        """Test error with custom message"""
        message = "Document type not applicable"
        with self.assertRaises(NotApplicableError) as context:
            raise NotApplicableError(message)
        self.assertIn(message, str(context.exception))


class TestAlreadyGeneratedError(unittest.TestCase):
    """Test AlreadyGeneratedError exception"""

    def test_already_generated_error_can_be_created(self):
        """Test that error can be created"""
        error = AlreadyGeneratedError("e-Invoice already generated")
        self.assertIsInstance(error, Exception)

    def test_already_generated_error_can_be_raised(self):
        """Test that error can be raised"""
        with self.assertRaises(AlreadyGeneratedError):
            raise AlreadyGeneratedError()

    def test_already_generated_error_with_message(self):
        """Test error with custom message"""
        message = "e-Waybill already exists"
        with self.assertRaises(AlreadyGeneratedError) as context:
            raise AlreadyGeneratedError(message)
        self.assertIn(message, str(context.exception))


class TestExceptionHierarchy(unittest.TestCase):
    """Test exception inheritance hierarchy"""

    def test_gsp_limit_exceeded_inherits_from_gsp_server_error(self):
        """Test inheritance chain"""
        self.assertTrue(issubclass(GSPLimitExceededError, GSPServerError))

    def test_gateway_timeout_inherits_from_gsp_server_error(self):
        """Test inheritance chain"""
        self.assertTrue(issubclass(GatewayTimeoutError, GSPServerError))

    def test_not_applicable_error_is_exception(self):
        """Test that NotApplicableError is an Exception"""
        self.assertTrue(issubclass(NotApplicableError, Exception))

    def test_already_generated_error_is_exception(self):
        """Test that AlreadyGeneratedError is an Exception"""
        self.assertTrue(issubclass(AlreadyGeneratedError, Exception))

    def test_otp_requested_error_is_exception(self):
        """Test that OTPRequestedError is an Exception"""
        self.assertTrue(issubclass(OTPRequestedError, Exception))

    def test_invalid_otp_error_is_exception(self):
        """Test that InvalidOTPError is an Exception"""
        self.assertTrue(issubclass(InvalidOTPError, Exception))

    def test_invalid_auth_token_error_is_exception(self):
        """Test that InvalidAuthTokenError is an Exception"""
        self.assertTrue(issubclass(InvalidAuthTokenError, Exception))


if __name__ == "__main__":
    unittest.main()
