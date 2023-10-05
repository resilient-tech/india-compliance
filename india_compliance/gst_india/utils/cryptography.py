import hmac
from base64 import b64decode, b64encode
from hashlib import sha256

from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad, unpad
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from frappe.utils import now_datetime

from india_compliance.gst_india.utils.__init__ import get_data_file_path

BS = 16
GSTN_CERTIFICATE = get_data_file_path("GSTN_G2B_Prod_public.cer")


def aes_encrypt_data(data, key):  # will encrypt the given string
    raw = pad(data.encode(), BS)
    if isinstance(key, str):
        key = key.encode()

    cipher = AES.new(key, AES.MODE_ECB)
    enc = cipher.encrypt(raw)

    return b64encode(enc).decode()


def aes_decrypt_data(encrypted, key):
    if isinstance(key, str):
        key = key.encode()

    encrypted = b64decode(encrypted)
    cipher = AES.new(key, AES.MODE_ECB)
    decrypted = unpad(cipher.decrypt(encrypted), BS)
    return decrypted


def hmac_sha256(data, key):
    hmac_value = hmac.new(key, data, sha256)

    return str(b64encode(hmac_value.digest()), "utf-8")


def encrypt_using_public_key(data, key=None):
    # TODO: save cert file in site and get path dynamically and check if expired to get latest path
    if not data:
        return

    if not key:
        key = GSTN_CERTIFICATE

    with open(key, "rb") as f:
        cert = x509.load_pem_x509_certificate(f.read(), default_backend())

    valid_up_to = cert.not_valid_after
    if valid_up_to < now_datetime():
        raise Exception("Certificate has expired")

    public_key = cert.public_key()
    pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    key = RSA.importKey(pem)

    cipher = PKCS1_v1_5.new(key)
    if isinstance(data, str):
        data = data.encode()

    ciphertext = cipher.encrypt(data)

    return b64encode(ciphertext).decode()
