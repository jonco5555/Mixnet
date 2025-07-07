from typing import Tuple

from nacl.encoding import Base64Encoder
from nacl.exceptions import CryptoError
from nacl.public import PrivateKey, PublicKey, SealedBox


def generate_key_pair(pubkey_path: str) -> Tuple[bytes, bytes]:
    """Generate a NaCl key pair and return private and public keys (Base64 encoded)."""
    privkey = PrivateKey.generate()
    pubkey = privkey.public_key

    # Serialize keys as Base64
    privkey_b64 = privkey.encode(encoder=Base64Encoder)
    pubkey_b64 = pubkey.encode(encoder=Base64Encoder)

    # Write public key to file
    with open(pubkey_path, "wb") as f:
        f.write(pubkey_b64)
    return privkey_b64, pubkey_b64


def encrypt(message: bytes, pubkey_b64: bytes) -> bytes:
    """Encrypt a message using the recipient's public key (SealedBox)."""
    pubkey = PublicKey(pubkey_b64, encoder=Base64Encoder)
    sealed_box = SealedBox(pubkey)
    ciphertext = sealed_box.encrypt(message)
    return ciphertext


def decrypt(ciphertext: bytes, privkey_b64: bytes) -> bytes:
    """Decrypt a message using the recipient's private key (SealedBox)."""
    privkey = PrivateKey(privkey_b64, encoder=Base64Encoder)
    sealed_box = SealedBox(privkey)
    try:
        plaintext = sealed_box.decrypt(ciphertext)
        return plaintext
    except CryptoError:
        raise ValueError("Decryption failed. Invalid key or corrupted ciphertext.")
