import os
import tempfile

import pytest
from nacl.encoding import Base64Encoder
from nacl.public import PrivateKey

from src.mixnet import crypto


def test_generate_key_pair_creates_valid_keys_and_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        pubkey_path = os.path.join(tmpdir, "test.key")
        privkey_b64, pubkey_b64 = crypto.generate_key_pair(pubkey_path)
        # Check that the file was created and contains the correct public key
        with open(pubkey_path, "rb") as f:
            file_pubkey = f.read()
        assert file_pubkey == pubkey_b64
        # Check that keys can be loaded
        priv = PrivateKey(privkey_b64, encoder=Base64Encoder)
        pub = priv.public_key
        assert pub.encode(encoder=Base64Encoder) == pubkey_b64


def test_encrypt_and_decrypt_success():
    privkey = PrivateKey.generate()
    pubkey = privkey.public_key
    privkey_b64 = privkey.encode(encoder=Base64Encoder)
    pubkey_b64 = pubkey.encode(encoder=Base64Encoder)
    message = b"hello, mixnet!"
    ciphertext = crypto.encrypt(message, pubkey_b64)
    assert ciphertext != message
    plaintext = crypto.decrypt(ciphertext, privkey_b64)
    assert plaintext == message


def test_decrypt_with_wrong_key_fails():
    privkey1 = PrivateKey.generate()
    privkey2 = PrivateKey.generate()
    pubkey1_b64 = privkey1.public_key.encode(encoder=Base64Encoder)
    privkey2_b64 = privkey2.encode(encoder=Base64Encoder)
    message = b"test message"
    ciphertext = crypto.encrypt(message, pubkey1_b64)
    with pytest.raises(ValueError, match="Decryption failed"):
        crypto.decrypt(ciphertext, privkey2_b64)


def test_encrypt_with_invalid_pubkey_raises():
    message = b"test"
    # Invalid base64 (not a valid key)
    bad_pubkey = b"notavalidkey=="
    with pytest.raises(Exception):
        crypto.encrypt(message, bad_pubkey)


def test_decrypt_with_invalid_privkey_raises():
    ciphertext = b"notarealciphertext"
    bad_privkey = b"notavalidkey=="
    with pytest.raises(Exception):
        crypto.decrypt(ciphertext, bad_privkey)


def test_double_encryption_and_decryption():
    # Generate two key pairs
    privkey1 = PrivateKey.generate()
    pubkey1 = privkey1.public_key
    privkey2 = PrivateKey.generate()
    pubkey2 = privkey2.public_key
    privkey1_b64 = privkey1.encode(encoder=Base64Encoder)
    pubkey1_b64 = pubkey1.encode(encoder=Base64Encoder)
    privkey2_b64 = privkey2.encode(encoder=Base64Encoder)
    pubkey2_b64 = pubkey2.encode(encoder=Base64Encoder)
    message = b"double encryption test payload"
    ciphertext1 = crypto.encrypt(message, pubkey1_b64)
    ciphertext2 = crypto.encrypt(ciphertext1, pubkey2_b64)
    decrypted1 = crypto.decrypt(ciphertext2, privkey2_b64)
    assert decrypted1 == ciphertext1
    decrypted2 = crypto.decrypt(decrypted1, privkey1_b64)
    assert decrypted2 == message
