import os
import threading
from concurrent import futures
from typing import Dict, List

import grpc

from mixnet.crypto import decrypt, generate_key_pair
from mixnet.mixnet_pb2 import (
    ForwardMessageRequest,
    ForwardMessageResponse,
    PollMessagesResponse,
)
from mixnet.mixnet_pb2_grpc import (
    MixServerServicer,
    MixServerStub,
    add_MixServerServicer_to_server,
)
from mixnet.models import Message


class MixServer(MixServerServicer):
    def __init__(
        self,
        id: str,
        port: int,
        messages_per_round: int,
        clients_addrs: List[str],
        config_dir: str,
    ):
        self._id = id
        self._messages_per_round = messages_per_round
        self._clients_addrs = clients_addrs
        self._pubkey_path = os.path.join(config_dir, f"{id}_pubkey.pem")
        self._private_key, self._private_key_pem, self._public_key = generate_key_pair(
            self._pubkey_path
        )
        self._round = 0
        self._messages: Dict[int, List[Message]] = {}
        self._cond = threading.Condition()
        self._final_messages: Dict[str, List[bytes]] = {}
        self._running = False

        # Create a gRPC server
        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        add_MixServerServicer_to_server(self, self._server)
        self._server.add_insecure_port(f"[::]:{port}")

    def start(self):
        self._running = True
        self._server.start()
        self._forward_thread = threading.Thread(target=self._wait_for_round_messages)
        self._forward_thread.start()
        # self._server.wait_for_termination()
        # with self._cond:
        #     self._cond.notify()  # Wake up forwarding thread to check running flag
        # self._forward_thread.join()

    def ForwardMessage(self, request, context):
        print(
            f"[{self._id}] Received message: '{request.payload}', round: {request.round}"
        )
        message = decrypt(request.payload, self._private_key_pem)
        message = Message.model_validate_json(message.decode())
        with self._cond:
            # Store the message
            if request.round not in self._messages:
                self._messages[request.round] = []
            self._messages[request.round].append(message)
            if len(self._messages[request.round]) == self._messages_per_round:
                self._cond.notify()
        return ForwardMessageResponse(
            status=f"Message '{message}' received for round {request.round}"
        )

    def _wait_for_round_messages(self):
        while self._running:
            with self._cond:
                self._cond.wait()
                if not self._running:
                    break

                messages = self._messages.pop(self._round)
                current_round = self._round
                self._round += 1

            self._send_round_messages(messages, current_round)

    def _send_round_messages(self, messages: List[Message], round: int):
        for message in messages:
            if message.address in self._clients_addrs:
                print(
                    f"[{self._id}] Received message for address {message.address} to poll: {message.payload}"
                )
                self._final_messages[message.address] = message.payload
            else:
                print(
                    f"[{self._id}] Forwarding round {round} messages to {message.address}"
                )
                with grpc.insecure_channel(message.address) as channel:
                    stub = MixServerStub(channel)
                    req = ForwardMessageRequest(payload=message.payload, round=round)
                    response = stub.ForwardMessage(req)
                    print(f"[{self._id}] Server responded: {response.status}")

    def PollMessages(self, request, context):
        client_address = request.client_id
        print(f"[{self._id}] PollMessages called for address: {client_address}")
        payloads = []
        if client_address in self._final_messages:
            payloads.append(self._final_messages.pop(client_address))
        return PollMessagesResponse(payloads=payloads)

    def stop(self):
        self._running = False
        with self._cond:
            self._cond.notify()  # Wake up forwarding thread to check running flag
        self._forward_thread.join()
        if self._server:
            self._server.stop(grace=5.0)
        if os.path.exists(self._pubkey_path):
            os.remove(self._pubkey_path)
