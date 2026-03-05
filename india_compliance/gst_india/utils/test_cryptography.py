"""
Unit tests for cryptography utility functions.
"""

import unittest
from base64 import b64decode, b64encode
from hashlib import sha256

import hmac

from india_compliance.gst_india.utils.cryptography import (
    aes_decrypt_data,
    aes_encrypt_data,
    hash_sha256,
    hmac_sha256,
)


class TestAESEncryption(unittest.TestCase):
    """Test AES encryption and decryption functions"""

    def test_aes_encrypt_decrypt_with_bytes_key(self):
        """Test encryption and decryption with bytes key"""
        data = "Hello World"
        key = b"0123456789abcdef"  # 16 bytes for AES-128

        encrypted = aes_encrypt_data(data, key)
        decrypted = aes_decrypt_data(encrypted, key)

        self.assertEqual(decrypted.decode(), data)

    def test_aes_encrypt_decrypt_with_string_key(self):
        """Test encryption and decryption with string key"""
        data = "Sensitive Information"
        key = "0123456789abcdef"  # 16 bytes for AES-128

        encrypted = aes_encrypt_data(data, key)
        decrypted = aes_decrypt_data(encrypted, key)

        self.assertEqual(decrypted.decode(), data)

    def test_aes_encrypt_returns_base64_string(self):
        """Test that encryption returns base64 encoded string"""
        data = "Test Data"
        key = b"0123456789abcdef"

        encrypted = aes_encrypt_data(data, key)

        # Should be a string
        self.assertIsInstance(encrypted, str)

        # Should be valid base64
        try:
            b64decode(encrypted)
        except Exception as self.fail("Encrypted data is not valid base64"):
            pass

    def test_aes_encrypt_different_keys_produce_different_ciphertexts(self):
        """Test that different keys produce different ciphertexts"""
        data = "Test Data"
        key1 = b"0123456789abcdef"
        key2 = b"fedcba9876543210"

        encrypted1 = aes_encrypt_data(data, key1)
        encrypted2 = aes_encrypt_data(data, key2)

        self.assertNotEqual(encrypted1, encrypted2)

    def test_aes_encrypt_same_data_produces_consistent_output(self):
        """Test that same data and key produce same ciphertext in ECB mode"""
        data = "Test Data"
        key = b"0123456789abcdef"

        encrypted1 = aes_encrypt_data(data, key)
        encrypted2 = aes_encrypt_data(data, key)

        # In ECB mode with same key, same plaintext produces same ciphertext
        self.assertEqual(encrypted1, encrypted2)

    def test_aes_encrypt_empty_string(self):
        """Test encryption of empty string"""
        data = ""
        key = b"0123456789abcdef"

        encrypted = aes_encrypt_data(data, key)
        decrypted = aes_decrypt_data(encrypted, key)

        self.assertEqual(decrypted.decode(), data)

    def test_aes_encrypt_unicode_data(self):
        """Test encryption of unicode data"""
        data = "नमस्ते"  # Unicode text
        key = b"0123456789abcdef"

        encrypted = aes_encrypt_data(data, key)
        decrypted = aes_decrypt_data(encrypted, key)

        self.assertEqual(decrypted.decode(), data)

    def test_aes_encrypt_long_string(self):
        """Test encryption of long string"""
        data = "A" * 1000
        key = b"0123456789abcdef"

        encrypted = aes_encrypt_data(data, key)
        decrypted = aes_decrypt_data(encrypted, key)

        self.assertEqual(decrypted.decode(), data)


class TestHMACAndHash(unittest.TestCase):
    """Test HMAC and hash functions"""

    def test_hmac_sha256_with_bytes_key(self):
        """Test HMAC SHA256 with bytes key"""
        data = "Test data"
        key = b"secret_key"

        result = hmac_sha256(data, key)

        # Verify it matches manual calculation
        expected = b64encode(
            hmac.new(key, data, sha256).digest()
        ).decode()
        self.assertEqual(result, expected)

    def test_hmac_sha256_deterministic(self):
        """Test that HMAC SHA256 is deterministic"""
        data = "Test data"
        key = b"secret_key"

        result1 = hmac_sha256(data, key)
        result2 = hmac_sha256(data, key)

        self.assertEqual(result1, result2)

    def test_hmac_sha256_different_keys_produce_different_hashes(self):
        """Test that different keys produce different HMAC values"""
        data = "Test data"
        key1 = b"key1"
        key2 = b"key2"

        result1 = hmac_sha256(data, key1)
        result2 = hmac_sha256(data, key2)

        self.assertNotEqual(result1, result2)

    def test_hmac_sha256_different_data_produces_different_hashes(self):
        """Test that different data produces different HMAC values"""
        data1 = "Test data 1"
        data2 = "Test data 2"
        key = b"secret_key"

        result1 = hmac_sha256(data1, key)
        result2 = hmac_sha256(data2, key)

        self.assertNotEqual(result1, result2)

    def test_hmac_sha256_returns_base64_string(self):
        """Test that HMAC SHA256 returns base64 encoded string"""
        data = "Test data"
        key = b"secret_key"

        result = hmac_sha256(data, key)

        # Should be a string
        self.assertIsInstance(result, str)

        # Should be valid base64
        try:
            b64decode(result)
        except Exception as self.fail("HMAC result is not valid base64"):
            pass

    def test_hash_sha256(self):
        """Test SHA256 hash function"""
        data = b"Test data"

        result = hash_sha256(data)

        # Verify it matches manual calculation
        expected = sha256(data).hexdigest()
        self.assertEqual(result, expected)

    def test_hash_sha256_deterministic(self):
        """Test that SHA256 is deterministic"""
        data = b"Test data"

        result1 = hash_sha256(data)
        result2 = hash_sha256(data)

        self.assertEqual(result1, result2)

    def test_hash_sha256_different_data_produces_different_hashes(self):
        """Test that different data produces different hashes"""
        data1 = b"Test data 1"
        data2 = b"Test data 2"

        result1 = hash_sha256(data1)
        result2 = hash_sha256(data2)

        self.assertNotEqual(result1, result2)

    def test_hash_sha256_returns_hex_string(self):
        """Test that SHA256 returns hex string"""
        data = b"Test data"

        result = hash_sha256(data)

        # Should be a string
        self.assertIsInstance(result, str)

        # Should be valid hex
        try:
            int(result, 16)
        except ValueError as self.fail("Hash is not valid hex"):
            pass

        # Should be 64 characters (256 bits = 32 bytes = 64 hex chars)
        self.assertEqual(len(result), 64)


if __name__ == "__main__":
    unittest.main()
