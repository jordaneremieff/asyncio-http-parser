import enum
import logging
import asyncio
from functools import partial
from typing import List
from dataclasses import dataclass
from contextvars import ContextVar


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()


parsing_data = ContextVar("parsing_data", default=None)
request_headers = ContextVar("request_headers", default=None)
request_info = ContextVar("request_info", default=b"")
parsing_ended = ContextVar("parsing_ended", default=False)


def set_header(data):
    _request_headers = request_headers.get()
    _parsing_data = parsing_data.get()

    if _parsing_data is None:
        parsing_data.set(data)
    else:
        parsing_data.set(_parsing_data + data)

    _parsing_data = parsing_data.get()

    for i in range(len(_parsing_data)):

        n = i + 1
        chunk = _parsing_data[i:n]

        if chunk == b"\r":
            _pos = n + 1

            _header = _parsing_data[:_pos]

            if _request_headers is None:
                request_info.set(_header)
                request_headers.set([])
                parsing_data.set(_parsing_data[_pos:])
            else:
                _request_headers.append(_header)
                request_headers.set(_request_headers)
                parsing_data.set(_parsing_data[_pos:])

            _parsing_data = parsing_data.get()
            look_ahead = _parsing_data[:2]
            if look_ahead == b"\r\n":
                parsing_ended.set(True)


class HTTPRequestState(enum.Enum):

    CONNECTING = 0
    CONNECTED = 1


@dataclass
class HTTPParser(asyncio.BufferedProtocol):

    buffer_data: bytearray = bytearray(100)
    request_state: HTTPRequestState = HTTPRequestState.CONNECTING
    headers: List = None

    def eof_received(self) -> None:
        pass

    def get_buffer(self, size: int) -> bytearray:
        if len(self.buffer_data) < size:
            self.buffer_data.extend(0 for _ in range(size - len(self.buffer_data)))
        return self.buffer_data

    def buffer_updated(self, nbytes: int) -> None:
        data = self.buffer_data[:nbytes]
        self.buffer_data_size += nbytes
        if self.request_state is HTTPRequestState.CONNECTING:

            set_header(data)
            _parsing_ended = parsing_ended.get()

            if _parsing_ended:
                self.state = HTTPRequestState.CONNECTED
                headers = request_headers.get()
                self.headers = headers
                self.on_headers_complete()

    def on_headers_complete(self):
        print(self.headers)

    # def get_http_version(self) -> str:

    # def should_keep_alive(self) -> bool:

    # def should_upgrade(self) -> bool:

    # def get_method(self) -> bytes:


SERVERS = []


async def create_protocol_server(host: str, port: int) -> None:
    loop = asyncio.get_running_loop()
    protocol = partial(HTTPParser, loop=loop)
    server = await loop.create_server(protocol, host=host, port=port)
    SERVERS.append(server)


def run():
    host = "0.0.0.0"
    port = 8000

    # Some issue with uvloop here... need to investigate
    # loop = uvloop.new_event_loop()
    # logger.warning("Running with uvloop...")

    loop = asyncio.new_event_loop()
    logger.warning("Running with asyncio...")

    asyncio.set_event_loop(loop)
    loop.set_debug(1)

    loop.create_task(create_protocol_server(host, port))

    logger.warning("Running protocol server on %s:%s" % (host, port))

    try:
        loop.run_forever()
    except Exception as exc:
        logger.debug("Exception in event loop: %s" % exc)
    finally:

        logger.warning("Closing protocol server on %s:%s" % (host, port))


if __name__ == "__main__":
    run()
