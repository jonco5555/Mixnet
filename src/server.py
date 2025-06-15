import threading
from concurrent import futures

import grpc

import mixnet_pb2
import mixnet_pb2_grpc


class MixServer(mixnet_pb2_grpc.MixServerServicer):
    def __init__(self, name, next_host=None):
        self._name = name
        self._next_host = next_host
        self._received_messages = {}
        self._round = 0
        self._messages_per_round = 1
        self._cond = threading.Condition()
        self._monitor_thread = threading.Thread(
            target=self._monitor_and_forward, daemon=True
        )
        self._monitor_thread.start()

    def _monitor_and_forward(self):
        while True:
            with self._cond:
                self._cond.wait()
                # Forward all messages for the current round
                if self._next_host and self._round in self._received_messages:
                    print(
                        f"[{self._name}] Forwarding round {self._round} messages to {self._next_host}"
                    )
                    with grpc.insecure_channel(self._next_host) as channel:
                        stub = mixnet_pb2_grpc.MixServerStub(channel)
                        for payload in self._received_messages[self._round]:
                            req = mixnet_pb2.ForwardMessageRequest(
                                payload=payload, round=self._round
                            )
                            try:
                                stub.ForwardMessage(req)
                            except Exception as e:
                                print(f"[{self._name}] Error forwarding message: {e}")
                # Prepare for next round
                self._round += 1
                # No need to clear, just wait for next round

    def ForwardMessage(self, request, context):
        print(
            f"[{self._name}] Received message: '{request.payload}', round: {request.round}"
        )
        with self._cond:
            # Store the message
            if request.round not in self._received_messages:
                self._received_messages[request.round] = []
            self._received_messages[request.round].append(request.payload)
            # Notify the monitor thread if the condition is met
            if (
                request.round == self._round
                and len(self._received_messages[self._round])
                == self._messages_per_round
            ):
                self._cond.notify_all()

        return mixnet_pb2.ForwardMessageResponse(
            status=f"Message '{request.payload}' received for round {request.round}"
        )


def serve(name, port, next_host=None):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    mixnet_pb2_grpc.add_MixServerServicer_to_server(MixServer(name, next_host), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"[{name}] Running on port {port}")
    server.wait_for_termination()
    return server
