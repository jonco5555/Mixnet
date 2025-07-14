import asyncio
import logging
import os
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
        round_duration: int = 1,
    ):
        self._logger = logging.getLogger(id)
        self._id = id
        self._messages_per_round = messages_per_round
        self._clients_addrs = clients_addrs
        self._output_dir = output_dir
        self._round_duration = round_duration
        self._port = port
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
        self._logger.info(f"Register called by: {request.client_id}")
        if len(self._registered_clients) >= self._messages_per_round:
            return RegisterResponse(status=False)
        self._registered_clients.add(request.client_id)
        if len(self._registered_clients) == self._messages_per_round:
            self._start_event.set()
        return RegisterResponse(status=True)

    async def WaitForStart(self, request, context):
        self._logger.info(f"WaitForStart called by: {context.peer()}")
        if not self._running:
            return WaitForStartResponse(ready=False)
        await self._start_event.wait()
        return WaitForStartResponse(ready=True, round_duration=self._round_duration)

    async def ForwardMessage(self, request, context):
        self._logger.info(
            f"Received message from: '{context.peer()}', round: {request.round}"
        )
        message = decrypt(request.payload, self._privkey_b64)
        message = Message.model_validate_json(message.decode())
        async with self._cond:
            # Store the message
            if request.round not in self._messages:
                self._messages[request.round] = []
            self._messages[request.round].append(message)
            if len(self._messages[request.round]) == self._messages_per_round:
                self._cond.notify()
        return ForwardMessageResponse(
            status=f"Message to '{message.address}' received for round {request.round}"
        )

    async def _wait_for_round_messages(self):
        while self._running:
            async with self._cond:
                await self._cond.wait()
                if not self._running:
                    break

                messages = self._messages.pop(self._round)
                current_round = self._round
                self._round += 1

            await self._send_round_messages(messages, current_round)

    async def _send_round_messages(self, messages: List[Message], round: int):
        for message in messages:
            if message.address in self._clients_addrs:
                self._logger.debug(
                    f"Received message for address {message.address} to poll"
                )
                if message.address not in self._final_messages:
                    self._final_messages[message.address] = []
                self._final_messages[message.address].append(message.payload)
                output_file = os.path.join(
                    self._output_dir,
                    f"{self._id}_round_{round}_{message.address.replace(':', '_')}.txt",
                )
                with open(output_file, "wb") as f:
                    f.write(message.payload)
            else:
                self._logger.info(
                    f"Forwarding round {round} messages to {message.address}"
                )
                async with grpc.aio.insecure_channel(message.address) as channel:
                    stub = MixServerStub(channel)
                    req = ForwardMessageRequest(payload=message.payload, round=round)
                    response = await stub.ForwardMessage(req)
                    self._logger.debug(f"Server responded: {response.status}")

    async def PollMessages(self, request, context):
        client_address = request.client_id
        self._logger.info(f"PollMessages called for address: {client_address}")
        payloads = self._final_messages.pop(client_address, [])
        return PollMessagesResponse(payloads=payloads)

    async def stop(self):
        self._running = False
        async with self._cond:
            self._cond.notify()  # Wake up forwarding thread to check running flag
        if self._server:
            await self._server.stop(grace=5.0)
        if self._wait_future:
            await self._wait_future
        if os.path.exists(self._pubkey_path):
            os.remove(self._pubkey_path)
        self._logger.info("Server stopped")
