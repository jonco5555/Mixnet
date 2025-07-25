import asyncio
import logging
import os
import time
from typing import Dict, List

import grpc

from mixnet.crypto import decrypt, generate_key_pair
from mixnet.mixnet_pb2 import (
    ForwardMessageRequest,
    ForwardMessageResponse,
    PollMessagesResponse,
    RegisterResponse,
    WaitForStartResponse,
)
from mixnet.mixnet_pb2_grpc import (
    MixServerServicer,
    MixServerStub,
    add_MixServerServicer_to_server,
)
from mixnet.models import Message

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


class MixServer(MixServerServicer):
    def __init__(
        self,
        id: str,
        port: int,
        messages_per_round: int,
        clients_addrs: List[str],
        config_dir: str,
        output_dir: str,
        round_duration: float = 1,
        enable_metrics: bool = False,
        metrics: Dict[str, float] = {},
    ):
        self._logger = logging.getLogger(id)
        self._id = id
        self._messages_per_round = messages_per_round
        self._clients_addrs = clients_addrs
        self._output_dir = output_dir
        self._round_duration = round_duration
        self._port = port
        self._enable_metrics = enable_metrics
        self._metrics = metrics
        self._server = None

        self._pubkey_path = os.path.join(config_dir, f"{id}.key")
        self._privkey_b64, self._pubkey_b64 = generate_key_pair(self._pubkey_path)
        self._round = 0
        self._messages: Dict[int, List[Message]] = {}
        self._cond = asyncio.Condition()
        self._final_messages: Dict[str, List[bytes]] = {}
        self._running = False
        self._registered_clients = set()
        self._start_event = asyncio.Event()
        self._wait_future = None

    async def start(self):
        # Create a gRPC server
        self._server = grpc.aio.server()
        add_MixServerServicer_to_server(self, self._server)
        self._server.add_insecure_port(f"[::]:{self._port}")
        self._running = True
        await self._server.start()
        self._wait_future = asyncio.create_task(self._wait_for_round_messages())
        self._logger.info(f"MixServer {self._id} started on port {self._port}")

    async def Register(self, request, context):
        """A gRPC API method for a client to register with the server.
        Sets start_event when the required number of clients is registered.

        Args:
            request (RegisterRequest): gRPC request containing client ID
            context (_type_): gRPC context

        Returns:
            RegisterResponse: gRPC response indicating registration status
        """
        self._logger.info(f"Client '{request.client_id}' attempting to register.")
        if len(self._registered_clients) >= self._messages_per_round:
            self._logger.warning(
                f"Registration failed for '{request.client_id}': server full."
            )
            return RegisterResponse(status=False)
        self._registered_clients.add(request.client_id)
        self._logger.info(
            f"Client '{request.client_id}' registered. Total: {len(self._registered_clients)}/{self._messages_per_round}"
        )
        if len(self._registered_clients) == self._messages_per_round:
            self._logger.info("All clients registered. Starting round.")
            self._start_event.set()
        return RegisterResponse(status=True)

    async def WaitForStart(self, request, context):
        """A gRPC API method for a client to wait for the server to be ready.
        The server does not send a response until all clients are registered.
        Once all clients are registered and start_event, a response is sent with
        the round duration, and the clients can start sending messages.

        Args:
            request (WaitForStartRequest): gRPC request containing client ID
            context (_type_): gRPC context

        Returns:
            WaitForStartResponse: gRPC response indicating readiness and round duration
        """
        self._logger.debug(f"WaitForStart called by: {context.peer()}")
        if not self._running:
            self._logger.warning("WaitForStart called but server is not running.")
            return WaitForStartResponse(ready=False)
        await self._start_event.wait()
        self._logger.info("All clients ready. Round is starting.")
        return WaitForStartResponse(ready=True, round_duration=self._round_duration)

    async def ForwardMessage(self, request, context):
        """A gRPC API method to receive messages from clients or other mix servers,
        decrypt them, and store them for processing and then forwarding for their destination.
        If received all messages for the current round, it notifies the waiting thread to start
        forwarding them.

        Args:
            request (ForwardMessageRequest): gRPC request containing the encrypted message and round number
            context (_type_): gRPC context

        Returns:
            ForwardMessageResponse: gRPC response indicating the status of the operation
        """
        if self._enable_metrics:
            received_time = time.perf_counter_ns()
        self._logger.info(
            f"Received message from: '{context.peer()}' for round {request.round}"
        )
        message = decrypt(request.payload, self._privkey_b64)
        message = Message.model_validate_json(message.decode())
        async with self._cond:
            # Store the message
            if request.round not in self._messages:
                self._messages[request.round] = []
                if request.round == 0 and self._enable_metrics:
                    self._metrics[self._id]["round_start_time"] = received_time
            self._messages[request.round].append(message)
            self._logger.debug(
                f"Stored message for round {request.round}. Count: {len(self._messages[request.round])}/{self._messages_per_round}"
            )
            if len(self._messages[request.round]) == self._messages_per_round:
                self._logger.info(
                    f"All messages received for round {request.round}. Notifying."
                )
                self._cond.notify()
        return ForwardMessageResponse(
            status=f"Message to '{message.address}' received for round {request.round}"
        )

    async def _wait_for_round_messages(self):
        """An asynchronous task that waits for all the round messages to be received.
        Once notified, it takes the messages from the dictionary and sends them.
        """
        while self._running:
            async with self._cond:
                await self._cond.wait()
                if not self._running:
                    break
                messages = self._messages.pop(self._round)
                current_round = self._round
                self._logger.info(
                    f"Processing round {current_round} with {len(messages)} messages."
                )
                self._round += 1
            await self._send_round_messages(messages, current_round)

    async def _send_round_messages(self, messages: List[Message], round: int):
        """If the message is for a registered client, it stores it in the final
        messages and saves the payload to a file.
        If the message is for another mix server, it forwards it to that server.

        Args:
            messages (List[Message]): messages to be sent in the current round
            round (int): the current round number
        """
        for message in messages:
            if message.address in self._clients_addrs:
                self._logger.info(
                    f"Received message for address {message.address} to poll"
                )
                if message.address not in self._final_messages:
                    self._final_messages[message.address] = []
                self._final_messages[message.address].append(message.payload)
                if self._enable_metrics:
                    round_end_time = time.perf_counter_ns()
                    if round == 0:
                        self._metrics[self._id]["round_end_time"] = round_end_time
                output_file = os.path.join(
                    self._output_dir,
                    f"{self._id}_round_{round}_{message.address.replace(':', '_')}.txt",
                )
                with open(output_file, "wb") as f:
                    f.write(message.payload)
            else:
                self._logger.info(
                    f"Forwarding round {round} message to server at '{message.address}'"
                )
                async with grpc.aio.insecure_channel(message.address) as channel:
                    stub = MixServerStub(channel)
                    req = ForwardMessageRequest(payload=message.payload, round=round)
                    response = await stub.ForwardMessage(req)
                    self._logger.debug(
                        f"Forwarded to {message.address}, response: {response.status}"
                    )

    async def PollMessages(self, request, context):
        """A gRPC API method for a client to pol messages.

        Args:
            request (PollMessagesRequest): gRPC request containing client address
            context (_type_): gRPC context

        Returns:
            PollMessagesResponse: gRPC response containing the list of messages
        """
        client_address = request.client_addr
        self._logger.info(f"Client '{client_address}' polling for messages.")
        payloads = self._final_messages.pop(client_address, [])
        self._logger.debug(
            f"Returned {len(payloads)} messages to client '{client_address}'."
        )
        return PollMessagesResponse(payloads=payloads)

    async def stop(self):
        self._logger.info("Stopping server")
        self._running = False
        async with self._cond:
            self._cond.notify()  # Wake up forwarding thread to check running flag
        if self._wait_future:
            await self._wait_future
        if self._server:
            await self._server.stop(grace=5.0)
        if os.path.exists(self._pubkey_path):
            os.remove(self._pubkey_path)
        self._logger.info("server stopped")
