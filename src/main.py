import time

from client import Client
from server import MixServer

if __name__ == "__main__":
    s1 = MixServer("server1", 50051, ["localhost:50053", "localhost:50054"])
    s2 = MixServer("server2", 50052, ["localhost:50053", "localhost:50054"])
    c1 = Client("client1", 50053)
    c2 = Client("client2", 50054)
    s1.start()
    s2.start()
    c1.prepare_message(
        "Hello, MixNet!", "localhost:50054", ["localhost:50051", "localhost:50052"], 0
    )
    time.sleep(1)
    c2.poll_messages("localhost:50051")
    s1.stop()
    s2.stop()
    print("Finished")
