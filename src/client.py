import grpc

import mixnet_pb2
import mixnet_pb2_grpc
from models import Message


class Client(mixnet_pb2_grpc.MixServerServicer):
    def __init__(self, name, port):
        self.name = name
        self.port = port
        self._client_id = f"localhost:{port}"

    def prepare_message(
        self, message: str, target: str, servers: list[str], round: int
    ):
        first_server = servers.pop()
        servers.insert(0, target)
        for server in servers:
            payload = Message(payload=message.encode(), address=server)
            message = payload.model_dump_json()
        self.send_message(first_server, message.encode(), round)

    def send_message(self, server, message, round):
        with grpc.insecure_channel(server) as channel:
            stub = mixnet_pb2_grpc.MixServerStub(channel)
            request = mixnet_pb2.ForwardMessageRequest(payload=message, round=round)
            response = stub.ForwardMessage(request)
            print(f"[{self.name}] Server responded: {response.status}")

    def poll_messages(self, server_host):
        with grpc.insecure_channel(server_host) as channel:
            stub = mixnet_pb2_grpc.MixServerStub(channel)
            request = mixnet_pb2.PollMessagesRequest(client_id=self._client_id)
            response = stub.PollMessages(request)
        for payload in response.payloads:
            print(f"[{self.name}] Polled message {payload.decode()}")

        return response.payloads
