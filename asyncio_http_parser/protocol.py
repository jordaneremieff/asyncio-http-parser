import enum
import logging
import asyncio
from typing import List, Tuple
from dataclasses import dataclass
from contextvars import ContextVar


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()


parsing_data = ContextVar("parsing_data", default=None)
parsing_header = ContextVar("parsing_header", default=b"")
last_header = ContextVar("last_header", default=b"")
headers_received = ContextVar("headers_received", default=False)
request_headers = ContextVar("request_headers", default=None)
request_info = ContextVar("request_info", default=b"")


def parse_headers(data):

    # Append new buffer data to existing parsing context data
    _parsing_data = parsing_data.get()
    if _parsing_data is not None:
        data = _parsing_data + data

    for i in range(len(data)):
        _parsing_header = parsing_header.get()

        b = data[i:i + 1]
        _parsing_header += b

        if b == b"\n":
            _request_headers = request_headers.get()
            _last_header = last_header.get()

            # Set the HTTP method and version
            if _request_headers is None:
                request_info.set(_parsing_header)
                request_headers.set([])

            elif _parsing_header == b"\r\n":
                # The previous header was the final one
                _last_header += _parsing_header
                _request_headers.append(_last_header)
                request_headers.set(_request_headers)
                # Inform the protocol
                headers_received.set(True)

            elif _last_header is not None:
                _request_headers.append(_last_header)
                request_headers.set(_request_headers)

            last_header.set(_parsing_header)
            parsing_header.set(b"")

        else:
            parsing_header.set(_parsing_header)

    if len(data):
        parsing_data.set(data)


class HTTPRequestState(enum.Enum):

    CONNECTING = 0
    RECEIVING = 1


@dataclass
class HTTPBufferedProtocol(asyncio.BufferedProtocol):

    transport: asyncio.BaseTransport
    loop: asyncio.BaseEventLoop
    buffer_data: bytearray = None
    request_state: HTTPRequestState = HTTPRequestState.CONNECTING
    request_headers: List = None
    request_info: bytes = None
    scheme: str = "http"
    http_version: str = "1.1"
    low_water_limit: int = 16384
    high_water_limit: int = 65536
    keep_alive: bool = True
    write_paused: bool = False
    read_paused: bool = False
    drain_waiter: asyncio.Event = asyncio.Event()

    def eof_received(self) -> None:
        pass

    def get_buffer(self, size: int) -> bytearray:
        if self.buffer_data is None:
            # todo: double-check this behaviour
            if size > 0:
                self.buffer_data = bytearray(size)
            else:
                self.buffer_data = bytearray(100)
        elif len(self.buffer_data) < size:
            self.buffer_data.extend(0 for _ in range(size - len(self.buffer_data)))
        return self.buffer_data

    def buffer_updated(self, nbytes: int) -> None:
        data = self.buffer_data[:nbytes]

        if self.request_state is HTTPRequestState.CONNECTING:
            parse_headers(data)

            if headers_received.get():
                self.request_state = HTTPRequestState.RECEIVING
                self.request_headers = request_headers.get()
                self.request_info = request_info.get()
                self.on_headers_complete()

        if self.request_state is HTTPRequestState.RECEIVING:
            print("Receiving")
            self.on_body(data)

    # async def drain(self) -> None:
    #     await self.drain_waiter.wait()

    # def pause_writing(self) -> None:
    #     assert not self.write_paused, "Invalid write state"
    #     self.write_paused = True
    #     self.drain_waiter.clear()

    # def resume_writing(self) -> None:
    #     assert self.write_paused, "Invalid write state"
    #     self.write_paused = False
    #     self.drain_waiter.set()

    def on_headers_complete(self):
        """Implemented on protocol"""

    def on_body(self, data):
        """Implemented on protocol"""

    def get_request_info(self) -> Tuple[bytes, bytes]:
        # print(_request_info)
        try:
            sep = self.request_info.index(b" /")
        except Exception as e:  # todo: fix this then remove exception
            for i in range(50):
                print(e)
                print(self.request_info)
            method, http_version = b"", b""
        else:
            end = len(self.request_info) - 2
            method, http_version = self.request_info[:sep], self.request_info[
                sep + 3:end
            ]
        return method, http_version

    def get_headers(self) -> List[List[bytes]]:
        headers = []
        for header in self.request_headers:
            # print(header)
            try:
                sep = header.index(b": ")
            except Exception as e:  # todo: handle this in parsing
                print(e)
                # print(header)
            else:
                end = len(header) - 2
                header = [header[:sep], header[sep + 2:end]]
                headers.append(header)
        return headers
