import os

import yaml
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from mixnet.models import Config, Entity


def generate_key_pair():
    """Generate an RSA key pair and return private and public keys."""
    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    public_key = private_key.public_key()
    # Serialize private key (PEM format, no encryption for simplicity)
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
    return private_key, private_key_pem, public_key_pem


def generate_config(
    num_clients: int, output_dir: str = "config", config_file: str = "config.yaml"
):
    """Generate key pairs for mix servers and clients, and create config.yaml.

    Args:
        num_clients: Number of clients to generate keys for.
        output_dir: Directory to save key files and config.yaml.
        config_file: Name of the configuration YAML file.
    """
    os.makedirs(output_dir, exist_ok=True)

    mix_servers = []
    clients = []

    # Generate keys for three mix servers
    for i in range(3):
        private_key, private_key_pem, public_key_pem = generate_key_pair()
        private_key_path = os.path.join(
            output_dir, f"mix_server_{i + 1}_private_key.pem"
        )
        print(private_key_path)
        with open(private_key_path, "wb") as f:
            f.write(private_key_pem)
        public_key_path = os.path.join(output_dir, f"mix_server_{i + 1}_public_key.pem")
        with open(public_key_path, "wb") as f:
            f.write(public_key_pem)
        # Use Entity model for mix server
        mix_servers.append(
            Entity(
                id=f"mix_server_{i + 1}",
                ip="localhost",
                port=50050 + i + 1,
                private_key_path=f"./mix_server_{i + 1}_private_key.pem",
                public_key_path=f"./mix_server_{i + 1}_public_key.pem",
            )
        )

    # Generate keys for clients
    for i in range(num_clients):
        private_key, private_key_pem, public_key_pem = generate_key_pair()
        private_key_path = os.path.join(output_dir, f"client_{i + 1}_private_key.pem")
        with open(private_key_path, "wb") as f:
            f.write(private_key_pem)
        public_key_path = os.path.join(output_dir, f"client_{i + 1}_public_key.pem")
        with open(public_key_path, "wb") as f:
            f.write(public_key_pem)
        # Use Entity model for client
        clients.append(
            Entity(
                id=f"client_{i + 1}",
                ip="localhost",
                port=50060 + i + 1,
                private_key_path=f"./client_{i + 1}_private_key.pem",
                public_key_path=f"./client_{i + 1}_public_key.pem",
            )
        )

    # Use Config model
    config = Config(
        messages_per_round=num_clients,
        mix_servers=mix_servers,
        clients=clients,
    )

    # Save configuration to YAML
    config_path = os.path.join(output_dir, config_file)
    with open(config_path, "w") as f:
        yaml.safe_dump(
            config.model_dump(), f, default_flow_style=False, sort_keys=False
        )
    print(f"Configuration saved to {config_path}")
    print(f"Key files saved to {output_dir}")


if __name__ == "__main__":
    # Generate config for 2 clients (can adjust for benchmarks: 2, 5, 10)
    generate_config(num_clients=2, output_dir="config")
