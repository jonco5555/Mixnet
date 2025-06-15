import os
from concurrent import futures

import grpc
import mixnet_pb2
import mixnet_pb2_grpc
import yaml
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class Client(mixnet_pb2_grpc.MixnetServiceServicer):
    def __init__(self, config_path: str, client_id: str, private_key_path: str):
        """Initialize the client with configuration and private key.

        Args:
            config_path: Path to the configuration YAML file.
            client_id: Unique identifier for the client (e.g., client_1).
            private_key_path: Path to the client's private key PEM file.
        """
        self._client_id = client_id
        # Load private key
        with open(private_key_path, "rb") as f:
            self._private_key = serialization.load_pem_private_key(
                f.read(), password=None, backend=default_backend()
            )
        # Load configuration
        with open(config_path, "r") as f:
            self._config = yaml.safe_load(f)
        self._config_dir = os.path.dirname(os.path.abspath(config_path))
        self._mix_servers = self._config["mix_servers"]
        self._clients = self._config["clients"]
        # Find own address for gRPC server
        self._address = next(
            c["address"] for c in self._clients if c["id"] == client_id
        )
        self._received_messages = []  # Store received messages
        self._channel = None
        self._stub = None
        self._server = None

    def load_public_key(self, key_path: str) -> rsa.RSAPublicKey:
        """Load an RSA public key from a PEM file."""
        abs_key_path = os.path.join(self._config_dir, key_path.lstrip("./"))
        with open(abs_key_path, "rb") as f:
            return serialization.load_pem_public_key(
                f.read(), backend=default_backend()
            )

    def prepare_message(self, message: bytes, recipient_id: str, round: int) -> bytes:
        """Prepare an onion-encrypted message for the mix network.

        Args:
            message: Plaintext message to send.
            recipient_id: ID of the recipient client (e.g., client_2).
            round: Round number for batch processing.

        Returns:
            Onion-encrypted payload as bytes.
        """
        # Find recipient's public key and address
        recipient = next((c for c in self._clients if c["id"] == recipient_id), None)
        if not recipient:
            raise ValueError(f"Recipient {recipient_id} not found in config")
        recipient_key = self._load_public_key(recipient["public_key_path"])
        recipient_address = recipient["address"]

        # Get mix server public keys (innermost to outermost)
        mix_pubkeys = [
            self._load_public_key(server["public_key_path"])
            for server in self._mix_servers
        ]

        # Step 1: Encrypt the message with recipient's public key (innermost layer)
        inner_encrypted = recipient_key.encrypt(
            message,  # Encrypt message directly, relying on OAEP padding
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )

        # Step 2: Build onion layers for each mix server
        payload = inner_encrypted
        for i, mix_key in enumerate(reversed(mix_pubkeys)):  # Outermost to innermost
            # Next hop: next mix server or recipient (for the last mix)
            next_hop = (
                self._mix_servers[len(mix_pubkeys) - i - 1]["address"]
                if i < len(mix_pubkeys) - 1
                else recipient_address
            )
            # Encode next hop address as fixed-length bytes (256 bytes)
            next_hop_bytes = next_hop.encode("utf-8").ljust(256, b"\0")
            # Combine inner payload and next hop
            payload = payload + next_hop_bytes
            # Encrypt with mix server's public key
            payload = mix_key.encrypt(
                payload,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )

        return payload

    def send_message(self, message: bytes, recipient_id: str, round: int):
        """Prepare and send an encrypted message to the first mix server.

        Args:
            message: Plaintext message to send.
            recipient_id: ID of the recipient client.
            round: Round number.
        """
        payload = self.prepare_message(message, recipient_id, round)
        first_mix_address = self._mix_servers[0]["address"]
        self._channel = grpc.insecure_channel(first_mix_address)
        self._stub = mixnet_pb2_grpc.MixnetServiceStub(self._channel)
        request = mixnet_pb2.ForwardMessageRequest(payload=payload, round=round)
        try:
            response = self._stub.ForwardMessage(request)
            if response.success:
                print(
                    f"[{self._client_id}] Message sent successfully for round {round}"
                )
            else:
                print(f"[{self._client_id}] Failed to send message for round {round}")
        except grpc.RpcError as e:
            print(f"[{self._client_id}] gRPC error sending message: {e}")
        finally:
            self._close()

    def ForwardMessage(
        self, request: mixnet_pb2.ForwardMessageRequest, context
    ) -> mixnet_pb2.ForwardResponse:
        """Handle incoming ForwardMessage RPC (receive and decrypt message).

        Args:
            request: ForwardMessageRequest containing payload and round.
            context: gRPC context.

        Returns:
            ForwardResponse indicating success or failure.
        """
        try:
            # Decrypt the payload with client's private key
            decrypted = self._private_key.decrypt(
                request.payload,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )
            # Store the message (no nonce to extract)
            self._received_messages.append(
                {
                    "round": request.round,
                    "message": decrypted.decode("utf-8", errors="ignore"),
                }
            )
            print(
                f"[{self._client_id}] Received message for round {request.round}: {decrypted}"
            )
            return mixnet_pb2.ForwardResponse(success=True)
        except Exception as e:
            print(
                f"[{self._client_id}] Error processing message for round {request.round}: {e}"
            )
            return mixnet_pb2.ForwardResponse(success=False)

    def start_server(self):
        """Start the gRPC server to receive messages."""
        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        mixnet_pb2_grpc.add_MixnetServiceServicer_to_server(self, self._server)
        self._server.add_insecure_port(self._address)
        self._server.start()
        print(f"[{self._client_id}] gRPC server started on {self._address}")
        self._server.wait_for_termination()

    def stop_server(self):
        """Stop the gRPC server."""
        if self._server:
            self._server.stop(None)
            print(f"[{self._client_id}] gRPC server stopped")

    def close(self):
        """Close the gRPC channel."""
        if self._channel:
            self._channel.close()
            self._channel = None
            self._stub = None


# Example usage
if __name__ == "__main__":
    from generate_keys import generate_config

    # Generate config and keys for 2 clients
    generate_config(num_clients=2, output_dir=".")

    # Initialize client
    client = Client("config.yaml", "client_1", "./client_1_private_key.pem")

    # Start gRPC server in a separate thread
    import threading

    server_thread = threading.Thread(target=client.start_server, daemon=True)
    server_thread.start()

    # Prepare and send a message
    message = b"Hello, anonymous world!"
    recipient_id = "client_2"
    round = 1
    client.send_message(message, recipient_id, round)

    # Keep the main thread alive (in practice, use a proper shutdown mechanism)
    import time

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        client.stop_server()
        client.close()
        client.close()
