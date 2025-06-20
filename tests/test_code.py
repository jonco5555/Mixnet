import time

from mixnet.client import Client
from mixnet.server import MixServer


def test_code():
    message = "Hello, Client!"
    s1 = MixServer("server1", 50051, 2, ["localhost:50053", "localhost:50054"])
    s2 = MixServer("server2", 50052, 2, ["localhost:50053", "localhost:50054"])
    c1 = Client("client1", 50053)
    c2 = Client("client2", 50054)
    s1.start()
    s2.start()
    c1.prepare_message(
        message, "localhost:50054", ["localhost:50051", "localhost:50052"], 0
    )
    time.sleep(1)
    results = c2.poll_messages("localhost:50051")
    s1.stop()
    s2.stop()

    assert results == [message.encode()]
