import time
from concurrent import futures

import grpc
import mixnet_pb2
import mixnet_pb2_grpc


class MixServer(mixnet_pb2_grpc.MixnetServiceServicer):
    def __init__(self, next_host=None):
        self.next_host = next_host

    def ForwardMessage(self, request, context):
        print(f"[Server] Received message: '{request.message}', round: {request.round}")

        if self.next_host:
            print(f"[Server] Forwarding to next server at {self.next_host}...")
            with grpc.insecure_channel(self.next_host) as channel:
                stub = mixnet_pb2_grpc.MixnetServiceStub(channel)
                request = mixnet_pb2.ForwardMessageRequest(request)
                response = stub.ForwardMessage(request)
                return response
        else:
            print("[Server] This is the last server. Done.")
            return mixnet_pb2.ForwardResponse(status="Delivered")


def serve(port, next_host=None):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    mixnet_pb2_grpc.add_MixnetServiceServicer_to_server(MixServer(next_host), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"[Server] Started on port {port}")
    return server
