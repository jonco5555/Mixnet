import threading
from concurrent import futures

import grpc

import mixnet_pb2
import mixnet_pb2_grpc


class Client(mixnet_pb2_grpc.MixServerServicer):
    def __init__(self, name, port):
        self.name = name
        self.port = port

    # # gRPC server method — receive messages
    # def ForwardMessage(self, request, context):
    #     print(
    #         f"[{self.name}] Received message: '{request.message}' (round {request.round})"
    #     )
    #     return mixnet_pb2.MessageResponse(status=f"Received by {self.name}")

    # # Start gRPC server to receive
    # def start_server(self):
    #     server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    #     mixnet_pb2_grpc.add_MixServerServicer_to_server(self, server)
    #     server.add_insecure_port(f"[::]:{self.port}")
    #     server.start()
    #     print(f"[{self.name}] Listening on port {self.port}")
    #     return server

    # gRPC client method — send message
    def send_message(self, target_host, message, round):
        with grpc.insecure_channel(target_host) as channel:
            stub = mixnet_pb2_grpc.MixServerStub(channel)
            request = mixnet_pb2.ForwardMessageRequest(payload=message, round=round)
            response = stub.ForwardMessage(request)
            print(f"[{self.name}] Server responded: {response.status}")
