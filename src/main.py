import threading
import time

from client import Client
from server import MixServer

if __name__ == "__main__":
    # t1 = threading.Thread(target=serve, args=("server1", 50051))
    # t1.start()
    s1 = MixServer("server1", 50051)
    t1 = threading.Thread(target=s1.start)
    t1.start()
    s2 = MixServer("server2", 50052, "localhost:50051")
    t2 = threading.Thread(target=s2.start)
    t2.start()
    c1 = Client("client1", 50053)
    c1.send_message("localhost:50052", b"Hello, MixNet!", 0)
    time.sleep(1)
    s1.stop()
    s2.stop()
    t1.join()
    t2.join()
    print("Finished")
