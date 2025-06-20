import threading
from concurrent import futures
from typing import List

import grpc

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
        self, name, port, messages_per_round: int, clients_addresses: List[str]
    ):
        self._name = name
        self._port = port
        self._round = 0
        self._messages_per_round = messages_per_round

        self._messages = {}
        self._cond = threading.Condition()
        self._final_messages = {}

        self._running = False

        self._clients_addresses = clients_addresses

        # Create a gRPC server
        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        add_MixServerServicer_to_server(self, self._server)
        self._server.add_insecure_port(f"[::]:{self._port}")

    def start(self):
        self._running = True
        self._server.start()
        self._forward_thread = threading.Thread(target=self._wait_for_round_messages)
        self._forward_thread.start()

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

    def _send_round_messages(self, messages: List[bytes], round: int):
        for message in messages:
            message = Message.model_validate_json(message.decode())
            if message.address in self._clients_addresses:
                print(
                    f"[{self._name}] Received message for address {message.address}: {message.payload}"
                )
                self._final_messages[message.address] = message.payload
            else:
                print(
                    f"[{self._name}] Forwarding round {round} messages to {message.address}"
                )
                with grpc.insecure_channel(message.address) as channel:
                    stub = MixServerStub(channel)
                    req = ForwardMessageRequest(payload=message.payload, round=round)
                    response = stub.ForwardMessage(req)
                    print(f"[{self._name}] Server responded: {response.status}")

    def ForwardMessage(self, request, context):
        print(
            f"[{self._name}] Received message: '{request.payload}', round: {request.round}"
        )
        with self._cond:
            # Store the message
            if request.round not in self._messages:
                self._messages[request.round] = []
            self._messages[request.round].append(request.payload)
            if len(self._messages[request.round]) == self._messages_per_round:
                self._cond.notify()
        return ForwardMessageResponse(
            status=f"Message '{request.payload}' received for round {request.round}"
        )

    def PollMessages(self, request, context):
        client_address = request.client_id
        print(f"[{self._name}] PollMessages called for address: {client_address}")
        payloads = []
        if client_address in self._final_messages:
            payloads.append(self._final_messages.pop(client_address))
        return PollMessagesResponse(payloads=payloads)

    # def send(self):
    #     with self._cond:
    #         self._cond.wait()
    #         with grpc.insecure_channel(self._next_host) as channel:
    #             stub = MixServerStub(channel)
    #             request = ForwardMessageRequest(
    #                 payload=self.messages[0], round=0
    #             )
    #             response = stub.ForwardMessage(request)
    #             print(f"[{self._next_host}] Server responded: {response.status}")

    def stop(self):
        self._running = False
        with self._cond:
            self._cond.notify()  # Wake up forwarding thread to check running flag
        self._forward_thread.join()
        if self._server:
            self._server.stop(grace=5.0)
