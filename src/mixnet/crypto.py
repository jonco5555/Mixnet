from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def generate_key_pair(pubkey_path: str) -> tuple:
    """Generate an RSA key pair and return private and public keys."""
    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    public_key = private_key.public_key()

    # Serialize private key (PEM format)
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    # Serialize public key (PEM format)
    public_key_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    # write public key to file
    with open(pubkey_path, "wb") as f:
        f.write(public_key_pem)
    return private_key, private_key_pem, public_key_pem


def encrypt(message: bytes, pubkey_pem: bytes) -> bytes:
    pubkey = serialization.load_pem_public_key(pubkey_pem, backend=default_backend())
    ciphertext = pubkey.encrypt(
        message,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return ciphertext


def decrypt(ciphertext: bytes, privkey_pem: bytes) -> bytes:
    privkey = serialization.load_pem_private_key(
        privkey_pem, password=None, backend=default_backend()
    )
    plaintext = privkey.decrypt(
        ciphertext,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return plaintext
