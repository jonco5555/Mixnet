from concurrent import futures

import grpc
import mixnet_pb2
import mixnet_pb2_grpc


# Final client acts as a gRPC server to receive messages
class Client(mixnet_pb2_grpc.MixnetServerServicer):
    def ForwardMessage(self, request, context):
        print(
            f"[Final Client] Message received: '{request.message}' at round {request.round}"
        )
        return mixnet_pb2.ForwardResponse(status="Received by Final Client")


def serve_final_client(port):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    mixnet_pb2_grpc.add_MixnetServiceServicer_to_server(Client(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"[Final Client] Listening on port {port}")
    return server


# Initial client that triggers the first server
def send_message(host, message, round):
    with grpc.insecure_channel(host) as channel:
        stub = mixnet_pb2_grpc.MixServerStub(channel)
        request = mixnet_pb2.MessageRequest(message=message, round=round)
        response = stub.ForwardMessage(request)
        print(f"[Initial Client] Server responded: {response.status}")
        response = stub.ForwardMessage(request)
        print(f"[Initial Client] Server responded: {response.status}")
