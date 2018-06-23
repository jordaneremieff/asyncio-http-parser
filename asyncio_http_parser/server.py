import asyncio
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, List, Tuple
import sys
import logging
from functools import partial
import argparse
import importlib
import time
import http
from email.utils import formatdate


from .parser import HTTPBufferedProtocol

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()


CURRENT_DATE = formatdate(time.time(), usegmt=True)

SERVER_NAME = "fikki"


def get_server_headers_bytes(status_code: int) -> List[Tuple]:
    try:
        phrase = http.HTTPStatus(status_code).phrase.encode()
    except ValueError:
        phrase = b""
    headers = [
        b"".join([b"HTTP/1.1 ", str(status_code).encode(), b" ", phrase, b"\r\n"]),
        b"".join([b"server: ", SERVER_NAME.encode(), b"\r\n"]),
        b"".join([b"date: ", CURRENT_DATE.encode(), b"\r\n"]),
    ]
    return headers


class ASGIConnectionState(Enum):
    STARTED = 0
    FINALIZING_HEADERS = 1
    SENDING_BODY = 2
    CLOSED = 3


@dataclass
class ASGIConnection:

    scope: dict
    transport: asyncio.BaseTransport
    protocol: asyncio.Protocol
    keep_alive: bool = True
    content_length: int = None
    chunked_encoding: bool = False
    state: ASGIConnectionState = ASGIConnectionState.STARTED
    receive_queue: asyncio.Queue = asyncio.Queue()

    def put_message(self, message: dict) -> None:
        self.protocol.get_buffer(len(message.get("body", b"")))
        self.receive_queue.put_nowait(message)

    async def receive(self) -> dict:
        return await self.receive_queue.get()

    async def send(self, message: dict) -> None:
        print(message)
        message_type = message['type']

        if message_type == 'http.response.start':
            if self.state is not ASGIConnectionState.STARTED:
                raise Exception("Unexpected 'http.response.start' message.")

            status = message["status"]
            headers = message.get("headers", [])

            content = get_server_headers_bytes(status)

            for header_name, header_value in headers:
                _header = header_name.lower()
                if _header == b"content-length":
                    self.content_length = int(header_value.decode())
                elif _header == b"connection":
                    if header_value.lower() == b"close":
                        self.keep_alive = False
                header = b"".join([header_name, b": ", header_value, b"\r\n"])
                content.append(header)

            if self.content_length is None:
                self.state = ASGIConnectionState.FINALIZING_HEADERS
            else:
                content.append(b"\r\n")
                self.state = ASGIConnectionState.SENDING_BODY
            # print(content)

            self.transport.write(b"".join(content))

        elif message_type == 'http.response.body':
            if self.state not in (ASGIConnectionState.SENDING_BODY, ASGIConnectionState.FINALIZING_HEADERS):
                raise Exception("Unexpected 'http.response.body' message.")
            # print(self.transport)

            body = message.get("body", b"")
            more_body = message.get("more_body", False)

            if self.state == ASGIConnectionState.FINALIZING_HEADERS:
                if more_body:
                    content = [
                        b"transfer-encoding: chunked\r\n\r\n",
                        b"%x\r\n" % len(body),
                        body,
                        b"\r\n",
                    ]
                    self.chunked_encoding = True
                    self.transport.write(b"".join(content))
                else:
                    content = [
                        b"content-length: ", str(len(body)).encode(), b"\r\n\r\n", body
                    ]
                    content = b"".join(content)
                    # print(content)
                    self.protocol.transport.write(content)

            elif self.state == ASGIConnectionState.SENDING_BODY:
                if self.chunked_encoding:
                    content = [b"%x\r\n" % len(body), body, b"\r\n"]
                    if not more_body:
                        content.append(b"0\r\n\r\n")
                    self.transport.write(b"".join(content))
                else:
                    self.transport.write(body)

            if more_body:
                self.state = ASGIConnectionState.SENDING_BODY
            else:
                self.state = ASGIConnectionState.CLOSED
                # self.transport.close()


class HTTPProtocol(HTTPBufferedProtocol):

    scope: dict = None
    # headers: List = field(default_factory=list)
    asgi_connection: ASGIConnection = None
    sockname: str = None
    peername: str = None

    def __init__(self, *, consumer: Any, loop: asyncio.AbstractEventLoop):
        self.consumer = consumer
        self.loop = loop

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        print("Connection made...")
        self.transport = transport
        self.sockname = self.transport.get_extra_info("sockname")
        self.peername = self.transport.get_extra_info("peername"),
        self.scheme = "https" if transport.get_extra_info("sslcontext") else "http"

    def connection_lost(self, exc) -> None:
        print("Connection lost...")
        if self.asgi_connection is not None:
            self.asgi_connection.put_message({"type": "http.disconnect"})
        self.transport = None

    def eof_received(self) -> None:
        pass

    def close(self) -> None:
        self.transport.close()

    def on_headers_complete(self):
        print("Headers received")
        # print(self.request_headers)
        method, http_version = self.get_request_info()
        path = b"/"  # todo

        headers = self.get_headers()
        print(headers)

        self.scope = {
            "type": "http",
            "http_version": http_version.decode("ascii"),
            "server": self.sockname,
            "client": self.peername,
            "scheme": self.scheme,
            "method": method.decode("ascii"),
            "path": path.decode("ascii"),
            "query_string": b"",  # todo
            "headers": headers,
        }

        asgi_connection = ASGIConnection(
            transport=self.transport, scope=self.scope, protocol=self, keep_alive=True
        )

        asgi_instance = self.consumer(asgi_connection.scope)
        self.loop.create_task(
            asgi_instance(asgi_connection.receive, asgi_connection.send)
        )
        asgi_connection.put_message({"type": "http.request", "body": b""})


@dataclass
class FikkiServer:

    servers: List = field(default_factory=list)
    connections: dict = field(default_factory=dict)

    async def create_protocol_server(
        self, app, host: str, port: int, protocol_class: asyncio.Protocol
    ) -> None:
        loop = asyncio.get_running_loop()
        protocol = partial(protocol_class, consumer=app, loop=loop)
        server = await loop.create_server(protocol, host=host, port=port)
        self.servers.append(server)
        print(self.servers)

    def run(self, app, *, host: str, port: int, uvloop: bool) -> None:
        # Some issue with this, need to resolve
        # if uvloop:
        #     import uvloop

        #     loop = uvloop.new_event_loop()
        #     logger.warning("Running with uvloop...")
        loop = asyncio.new_event_loop()
        logger.warning("Running with asyncio...")

        asyncio.set_event_loop(loop)
        loop.set_debug(1)

        loop.create_task(
            self.create_protocol_server(app, host, port, protocol_class=HTTPProtocol)
        )

        logger.warning("Running protocol server on %s:%s" % (host, port))

        try:
            loop.run_forever()
        except Exception as exc:
            logger.debug("Exception in event loop: %s" % exc)
        finally:

            logger.warning("Closing protocol server on %s:%s" % (host, port))


def main(args=None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("app", help="ASGI application")
    parser.add_argument("--host", default="0.0.0.0", help="Host")
    parser.add_argument("--port", default="8000", help="Port")
    parser.add_argument("--uvloop", action="store_true")
    args = parser.parse_args()
    app_module, asgi_callable = args.app.split(":")
    sys.path.insert(0, ".")
    app = getattr(importlib.import_module(app_module), asgi_callable)
    FikkiServer().run(app, host=args.host, port=args.port, uvloop=args.uvloop)


if __name__ == "__main__":
    main()
