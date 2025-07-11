import asyncio
import os
from typing import Dict, List

import grpc

from mixnet.crypto import decrypt, encrypt, generate_key_pair
from mixnet.mixnet_pb2 import (
    ForwardMessageRequest,
    PollMessagesRequest,
    RegisterRequest,
    WaitForStartRequest,
)
from mixnet.mixnet_pb2_grpc import MixServerServicer, MixServerStub
from mixnet.models import Message


class Client(MixServerServicer):
    def __init__(
        self, id: str, config_dir: str, mix_pubkeys: List[bytes], mix_addrs: List[str]
    ):
        self._id = id
        self._pubkey_path = os.path.join(config_dir, f"{id}.key")
        self._privkey_b64, self._pubkey_b64 = generate_key_pair(self._pubkey_path)
        self._running = False
        self._mix_pubkeys = mix_pubkeys
        self._mix_addrs = mix_addrs
        self._first_host = mix_addrs[0]
        self._messages: Dict[int, bytes] = {}
        self._round = 0
        self._run_forever_future = None

    async def start(self):
        print(f"[{self._id}] Client started")
        await self.register()
        round_duration = await self.wait_for_start()
        self._running = True
        self._run_forever_future = asyncio.create_task(self.run_forever(round_duration))

    async def run_forever(self, round_duration: int):
        while self._running:
            await asyncio.sleep(round_duration)
            if self._round not in self._messages:
                print(
                    f"[{self._id}] No messages for round {self._round}, creating a dummy"
                )
                await self.prepare_message("dummy", self._pubkey_b64, self._id)
            await self.send_message(
                self._messages[self._round], self._mix_addrs[0], self._round
            )
            self._round += 1

    async def stop(self):
        self._running = False
        if self._run_forever_future:
            await self._run_forever_future
        print(f"[{self._id}] Client stopped")

    async def register(self):
        async with grpc.aio.insecure_channel(self._first_host) as channel:
            stub = MixServerStub(channel)
            request = RegisterRequest(client_id=self._id)
            response = await stub.Register(request)
            if not response.status:
                raise Exception(f"Failed to register with server: {self._first_host}")
            print(f"[{self._id}] Registered with server: {self._first_host}")
            return response

    async def wait_for_start(self):
        async with grpc.aio.insecure_channel(self._first_host) as channel:
            stub = MixServerStub(channel)
            request = WaitForStartRequest(client_id=self._id)
            response = await stub.WaitForStart(request)
            if not response.ready:
                raise Exception(f"Server is not ready: {self._first_host}")
            print(
                f"[{self._id}] Server is ready: {self._first_host}, round duration: {response.round_duration}"
            )
            return response.round_duration

    async def prepare_message(
        self,
        message: str,
        recipient_pubkey: bytes,
        recipient_addr: str,
    ):
        round = self._round
        if round in self._messages:
            print(f"[{self._id}] Message for round {round} already prepared")
            if message == "dummy":
                print(f"[{self._id}] Dummy message for round {round} ignored")
                return
            round += 1
        print(f"[{self._id}] Preparing message for round {round} - {message}")
        pubkeys = [recipient_pubkey] + self._mix_pubkeys[::-1]
        addresses = [recipient_addr] + self._mix_addrs[::-1]
        for pubkey, addr in zip(pubkeys, addresses):
            ciphertext = encrypt(message.encode(), pubkey)
            message = Message(payload=ciphertext, address=addr).model_dump_json()
        self._messages[round] = ciphertext

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


"""I want the start method to go like this:
self should store the messages it built with prepare_message.
If after asyncio.sleep time, it does not have a message for the current round """
