import asyncio
import logging
import os
import time
from typing import Dict, List

import grpc

from mixnet.crypto import decrypt, encrypt, generate_key_pair
from mixnet.mixnet_pb2 import (
    ClientPollMessagesResponse,
    ForwardMessageRequest,
    PollMessagesRequest,
    PrepareMessageResponse,
    RegisterRequest,
    WaitForStartRequest,
)
from mixnet.mixnet_pb2_grpc import (
    ClientServicer,
    MixServerStub,
    add_ClientServicer_to_server,
)
from mixnet.models import Message

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


class Client(ClientServicer):
    def __init__(
        self,
        id: str,
        addr: str,
        port: int,
        config_dir: str,
        mix_pubkeys: List[bytes],
        mix_addrs: List[str],
        dummy_payload: str = "dummy",
        enable_metrics: bool = False,
        metrics: Dict[str, float] = {},
    ):
        self._logger = logging.getLogger(id)
        self._id = id
        self._addr = addr
        self._dummy_payload = dummy_payload
        self._pubkey_path = os.path.join(config_dir, f"{id}.key")
        self._privkey_b64, self._pubkey_b64 = generate_key_pair(self._pubkey_path)
        self._running = False
        self._mix_pubkeys = mix_pubkeys
        self._mix_addrs = mix_addrs
        self._first_host = mix_addrs[0]
        self._last_host = mix_addrs[-1]
        self._messages: Dict[int, bytes] = {}
        self._round = 0
        self._run_forever_future = None
        self._port = port
        self._listener = None
        self._enable_metrics = enable_metrics
        self._metrics = metrics

    async def start(self):
        self._logger.info("Client started")
        self._listener = grpc.aio.server()
        add_ClientServicer_to_server(self, self._listener)
        self._listener.add_insecure_port(f"[::]:{self._port}")
        await self.register()
        round_duration = await self.wait_for_start()
        await self._listener.start()
        self._running = True
        self._run_forever_future = asyncio.create_task(self.run_forever(round_duration))

    async def run_forever(self, round_duration: float):
        """Main loop for the client to send messages periodically
        Client sleeps for `round_duration` seconds and checks if there are messages to send.
        If no messages are found for the current round, it prepares a dummy message.
        Then it sends the message to the first mix server in the list.

        Args:
            round_duration (float): round duration in seconds
        """
        while self._running:
            await asyncio.sleep(round_duration)
            if self._round not in self._messages:
                self._logger.debug(
                    f"No messages for round {self._round}, creating a dummy"
                )
                await self._prepare_message(
                    self._dummy_payload, self._pubkey_b64, self._addr
                )
            await self.send_message(
                self._messages[self._round], self._mix_addrs[0], self._round
            )
            self._round += 1

    async def stop(self):
        self._logger.info("Stopping client")
        self._running = False
        if self._run_forever_future:
            await self._run_forever_future
        if self._listener:
            await self._listener.stop(grace=5.0)
        if os.path.exists(self._pubkey_path):
            os.remove(self._pubkey_path)
        self._logger.info("Client stopped")

    async def register(self):
        """Calls the server's gRPC mathod to register

        Raises:
            Exception: Failed to register

        Returns:
            RegisterResponse: response from the server
        """
        async with grpc.aio.insecure_channel(self._first_host) as channel:
            stub = MixServerStub(channel)
            request = RegisterRequest(client_id=self._id)
            response = await stub.Register(request)
            if not response.status:
                raise Exception(f"Failed to register with server: {self._first_host}")
            self._logger.info(f"Registered with server: {self._first_host}")
            return response

    async def wait_for_start(self):
        """Calls the server's gRPC method to wait for the server to be ready.
        Once the server is ready, it means the first round starts and the client
        should start sending messages.

        Raises:
            Exception: Server is not ready

        Returns:
            float: round duration in seconds
        """
        async with grpc.aio.insecure_channel(self._first_host) as channel:
            stub = MixServerStub(channel)
            request = WaitForStartRequest(client_id=self._id)
            response = await stub.WaitForStart(request)
            if not response.ready:
                raise Exception(f"Server is not ready: {self._first_host}")
            self._logger.info(
                f"Server is ready: {self._first_host}, round duration: {response.round_duration}"
            )
            return response.round_duration

    async def _prepare_message(
        self,
        message: str,
        recipient_pubkey: bytes,
        recipient_addr: str,
    ):
        """Prepares a message to be sent in the mixnet by encrypting it in layers like an onion.
        The message is encrypted with the recipient's public key and then with the public keys of
        the mix servers in reverse order.

        Args:
            message (str): the message to be sent
            recipient_pubkey (bytes): the public key of the recipient
            recipient_addr (str): the address of the recipient
        """
        round = self._round
        if round in self._messages:
            self._logger.debug(f"Message for round {round} already prepared")
            if message == self._dummy_payload:
                self._logger.debug(f"Dummy message for round {round} ignored")
                return
            round += 1
        if self._enable_metrics:
            prepare_start_time = time.perf_counter_ns()
            if round == 0:
                self._metrics[self._id]["prepare_start_time"] = prepare_start_time
        self._logger.info(f"Preparing message for round {round}")
        pubkeys = [recipient_pubkey] + self._mix_pubkeys[::-1]
        addresses = [recipient_addr] + self._mix_addrs[::-1]
        for pubkey, addr in zip(pubkeys, addresses):
            ciphertext = encrypt(message.encode(), pubkey)
            message = Message(payload=ciphertext, address=addr).model_dump_json()
        self._messages[round] = ciphertext
        if self._enable_metrics:
            prepare_end_time = time.perf_counter_ns()
            if round == 0:
                self._metrics[self._id]["prepare_end_time"] = prepare_end_time

    async def send_message(self, payload: bytes, addr: str, round: int):
        """Calls the server's gRPC method to forward the message to it.

        Args:
            payload (bytes): the encrypted message payload
            addr (str): the address of the mix server to send the message to
            round (int): the message round number
        """
        async with grpc.aio.insecure_channel(addr) as channel:
            stub = MixServerStub(channel)
            request = ForwardMessageRequest(payload=payload, round=round)
            response = await stub.ForwardMessage(request)
            self._logger.debug(f"Server responded: {response.status}")

    async def _poll_messages(self, server_host: str) -> List[str]:
        """Calls the server's gRPC method to poll messages from it.
        It decrypts the messages using the client's private key and returns a list of
        messages that are not dummy payloads.

        Args:
            server_host (str): the address of the mix server to poll messages from

        Returns:
            List[str]: list of decrypted messages that are not dummy payloads
        """
        async with grpc.aio.insecure_channel(server_host) as channel:
            stub = MixServerStub(channel)
            request = PollMessagesRequest(client_addr=self._addr)
            response = await stub.PollMessages(request)
        messages = []
        for payload in response.payloads:
            message = decrypt(payload, self._privkey_b64).decode()
            if message != self._dummy_payload:
                messages.append(message)
                self._logger.info("Polled message")
                self._logger.debug(f"{message=}")

        return messages

    async def PrepareMessage(self, request, context):
        """A gRPC API method to invoke _prepare_message

        Args:
            request (PrepareMessageRequest): gRPC request
            context (_type_): gRPC context

        Returns:
            PrepareMessageResponse: the response indicating the status of the operation
        """
        await self._prepare_message(
            request.message,
            request.recipient_pubkey,
            request.recipient_addr,
        )
        return PrepareMessageResponse(status=True)

    async def PollMessages(self, request, context):
        """A gRPC API method to invoke _poll_messages

        Args:
            request (ClientPollMessagesRequest): gRPC request
            context (_type_): gRPC context

        Returns:
            ClientPollMessagesResponse: the response containing the list of messages
        """
        messages = await self._poll_messages(self._last_host)
        return ClientPollMessagesResponse(messages=messages)
