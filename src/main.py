import threading
import time

from client import BidirectionalClient
from server import serve

# Ports
ports = {
    "client0": "50050",
    "server0": "50051",
    "server1": "50052",
    "server2": "50053",
    "client1": "50054",
}


def start_clients():
    client0 = BidirectionalClient("Client0", ports["client0"])
    client1 = BidirectionalClient("Client1", ports["client1"])

    # Start both as servers
    threading.Thread(target=client0.start_server).start()
    threading.Thread(target=client1.start_server).start()

    # Wait for servers to start
    time.sleep(2)

    # Send message from Client0 -> Server0
    client0.send_message(f"localhost:{ports['server0']}", "Hello from Client0", 1)

    # Send message from Client1 -> Server0 (test both ways)
    client1.send_message(f"localhost:{ports['server0']}", "Reply from Client1", 2)


def start_servers():
    threading.Thread(
        target=serve,
        args=("Server2", ports["server2"], f"localhost:{ports['client1']}"),
    ).start()
    threading.Thread(
        target=serve,
        args=("Server1", ports["server1"], f"localhost:{ports['server2']}"),
    ).start()
    threading.Thread(
        target=serve,
        args=("Server0", ports["server0"], f"localhost:{ports['server1']}"),
    ).start()


def main():
    start_servers()
    time.sleep(1)  # let servers boot
    start_clients()


if __name__ == "__main__":
    main()
