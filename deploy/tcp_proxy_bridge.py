from __future__ import annotations

import argparse
import select
import socket
import socketserver
import threading


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bridge a host-local TCP proxy to a container-accessible port")
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--target-host", default="127.0.0.1")
    parser.add_argument("--target-port", type=int, required=True)
    return parser.parse_args()


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class ProxyHandler(socketserver.BaseRequestHandler):
    target_host: str
    target_port: int

    def handle(self) -> None:
        upstream = socket.create_connection((self.target_host, self.target_port), timeout=10)
        upstream.settimeout(None)
        self.request.settimeout(None)
        sockets = [self.request, upstream]
        try:
            while True:
                readable, _, _ = select.select(sockets, [], [], 60)
                if not readable:
                    continue
                for current in readable:
                    data = current.recv(65536)
                    if not data:
                        return
                    peer = upstream if current is self.request else self.request
                    peer.sendall(data)
        finally:
            upstream.close()
            self.request.close()


def main() -> None:
    args = parse_args()

    class Handler(ProxyHandler):
        target_host = args.target_host
        target_port = args.target_port

    server = ThreadedTCPServer((args.listen_host, args.listen_port), Handler)
    print(
        f"tcp proxy bridge listening on {args.listen_host}:{args.listen_port}, "
        f"forwarding to {args.target_host}:{args.target_port}",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
