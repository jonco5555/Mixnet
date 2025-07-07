import os
from typing import List

import grpc

from mixnet.crypto import decrypt, encrypt, generate_key_pair
from mixnet.mixnet_pb2 import ForwardMessageRequest, PollMessagesRequest
from mixnet.mixnet_pb2_grpc import MixServerServicer, MixServerStub
from mixnet.models import Message


class Client(MixServerServicer):
    def __init__(self, id: str, config_dir: str):
        self._id = id
        self._pubkey_path = os.path.join(config_dir, f"{id}.key")
        self._privkey_b64, self._pubkey_b64 = generate_key_pair(self._pubkey_path)

    async def prepare_message(
        self,
        message: str,
        recipient_pubkey: bytes,
        recipient_addr: str,
        mix_pubkeys: List[bytes],
        mix_addrs: List[str],
        round: int,
    ):
        pubkeys = [recipient_pubkey] + mix_pubkeys
        addresses = [recipient_addr] + mix_addrs
        first_server_addr = addresses[-1]
        for pubkey, addr in zip(pubkeys, addresses):
            ciphertext = encrypt(message.encode(), pubkey)
            message = Message(payload=ciphertext, address=addr).model_dump_json()
        await self.send_message(ciphertext, first_server_addr, round)

    async def send_message(self, payload: bytes, addr: str, round):
        async with grpc.aio.insecure_channel(addr) as channel:
            stub = MixServerStub(channel)
            request = ForwardMessageRequest(payload=payload, round=round)
            response = await stub.ForwardMessage(request)
            print(f"[{self._id}] Server responded: {response.status}")

    async def poll_messages(self, server_host) -> List[str]:
        async with grpc.aio.insecure_channel(server_host) as channel:
            stub = MixServerStub(channel)
            request = PollMessagesRequest(client_id=self._id)
            response = await stub.PollMessages(request)
        messages = []
        for payload in response.payloads:
            message = decrypt(payload, self._privkey_b64).decode()
            messages.append(message)
            print(f"[{self._id}] Polled message {message}")

        return messages
