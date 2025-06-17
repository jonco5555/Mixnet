import threading
from concurrent import futures
from typing import List

import grpc

import mixnet_pb2
import mixnet_pb2_grpc


class MixServer(mixnet_pb2_grpc.MixServerServicer):
    def __init__(self, name, port, next_host=None):
        self._name = name
        self._port = port
        self._next_host = next_host
        self._received_messages = {}
        self._clients_messages = {}
        self._round = 0
        self._messages_per_round = 1
        self._cond = threading.Condition()
        self._stop = threading.Event()
        self._monitor_thread = threading.Thread(
            target=self._wait_for_round_messages, daemon=True
        )
        # self._monitor_thread.start()
        self._server = None
        self.messages = []
        threading.Thread(target=self.send).start()

    def _wait_for_round_messages(self):
        while not self._stop.is_set():
            with self._cond:
                self._cond.wait()
                messages = self._received_messages.pop(self._round)
                self._round += 1
            # Release the lock

            self._send_round_messages(messages)

    def _send_round_messages(self, messages: List[bytes]):
        # Forward all messages for the current round
        if self._next_host:
            print(
                f"[{self._name}] Forwarding round {self._round - 1} messages to {self._next_host}"
            )
            with grpc.insecure_channel(self._next_host) as channel:
                stub = mixnet_pb2_grpc.MixServerStub(channel)
                for payload in messages:
                    req = mixnet_pb2.ForwardMessageRequest(
                        payload=payload, round=self._round
                    )
                    response = stub.ForwardMessage(req)
                    print(f"[{self.name}] Server responded: {response.status}")

    def ForwardMessage(self, request, context):
        print(
            f"[{self._name}] Received message: '{request.payload}', round: {request.round}"
        )
        # if self._next_host:
        #     with self._cond:
        #         # Store the message
        #         if request.round not in self._received_messages:
        #             self._received_messages[request.round] = []
        #         self._received_messages[request.round].append(request.payload)
        #         # Notify the monitor thread if the condition is met
        #         if (
        #             len(self._received_messages[self._round])
        #             == self._messages_per_round
        #         ):
        #             self._cond.notify_all()

        if self._next_host:
            with self._cond:
                self.messages.append(request.payload)
                self._cond.notify()
        return mixnet_pb2.ForwardMessageResponse(
            status=f"Message '{request.payload}' received for round {request.round}"
        )

    def send(self):
        with self._cond:
            self._cond.wait()
            with grpc.insecure_channel(self._next_host) as channel:
                stub = mixnet_pb2_grpc.MixServerStub(channel)
                request = mixnet_pb2.ForwardMessageRequest(
                    payload=self.messages[0], round=0
                )
                response = stub.ForwardMessage(request)
                print(f"[{self._next_host}] Server responded: {response.status}")

    def start(self):
        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        mixnet_pb2_grpc.add_MixServerServicer_to_server(self, self._server)
        self._server.add_insecure_port(f"[::]:{self._port}")
        self._server.start()
        print(f"[{self._name}] Running on port {self._port}")
        self._stop.wait()

    def stop(self, grace=0):
        self._stop.set()
        self._server.stop(grace)
