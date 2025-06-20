import time

from client import Client
from server import MixServer

if __name__ == "__main__":
    s1 = MixServer("server1", 50051, 2, ["localhost:50055", "localhost:50054"])
    s2 = MixServer("server2", 50052, 2, ["localhost:50055", "localhost:50054"])
    s3 = MixServer("server3", 50053, 2, ["localhost:50055", "localhost:50054"])
    c1 = Client("client1", 50055)
    c2 = Client("client2", 50054)
    s1.start()
    s2.start()
    s3.start()
    c1.prepare_message(
        "Hello, client2!",
        "localhost:50054",
        ["localhost:50051", "localhost:50052", "localhost:50053"],
        0,
    )
    c2.prepare_message(
        "Hello, client1!",
        "localhost:50055",
        ["localhost:50051", "localhost:50052", "localhost:50053"],
        0,
    )
    time.sleep(1)
    print(c1.poll_messages("localhost:50051"))
    print(c2.poll_messages("localhost:50051"))
    s1.stop()
    s2.stop()
    s3.stop()
    print("Finished")
