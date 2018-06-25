import enum
import logging
import asyncio
from typing import List, Tuple
from dataclasses import dataclass, field
from contextvars import ContextVar


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()


parsing_data = ContextVar("parsing_data", default=None)
parsing_header = ContextVar("parsing_header", default=b"")
parsing_sep_pos = ContextVar("parsing_sep_pos", default=None)
next_sep_pos = ContextVar("next_sep_pos", default=None)
next_header = ContextVar("next_header", default=b"")

request_info = ContextVar("request_info", default=None)


class HTTPConnectionState(enum.Enum):

    CONNECTED = 0
    HEADERS_RECEIVED = 1


def parse_headers(data: bytes, protocol: asyncio.BaseProtocol) -> None:

    _parsing_data = parsing_data.get()
    if _parsing_data is not None:
        data = _parsing_data + data

    data_len = len(data)

    for i in range(data_len):
        _parsing_header = parsing_header.get()

        b = data[i:i + 1]
        _parsing_header += b
        data_len -= 1

        _request_info = request_info.get()

        if b == b":":
            _parsing_sep_pos = parsing_sep_pos.get()
            if _parsing_sep_pos is None and _request_info is not None:
                parsing_sep_pos.set(len(_parsing_header))

        if b == b"\n":

            if request_info.get() is None:
                request_info.set(_parsing_header)
            else:
                _next_header = next_header.get()

                if _next_header is not None and _next_header != b"":
                    _next_sep_pos = next_sep_pos.get()
                    _current_header = _next_header[:_next_sep_pos - 1]
                    _current_value = _next_header[
                        _next_sep_pos + 1:len(_next_header) - 2
                    ]
                    protocol.on_header(_current_header, _current_value)

                if _parsing_header == b"\r\n":
                    protocol.connection_state = HTTPConnectionState.HEADERS_RECEIVED

                _parsing_sep_pos = parsing_sep_pos.get()
                next_sep_pos.set(_parsing_sep_pos)
                next_header.set(_parsing_header)
                parsing_sep_pos.set(None)

            parsing_header.set(b"")
        else:
            parsing_header.set(_parsing_header)

    if data_len > 0:
        parsing_data.set(data)


@dataclass
class HTTPBufferedProtocol(asyncio.BufferedProtocol):

    transport: asyncio.BaseTransport
    loop: asyncio.BaseEventLoop
    buffer_data: bytearray = None
    connection_state: HTTPConnectionState = HTTPConnectionState.CONNECTED
    headers: List = field(default_factory=list)
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

        if self.connection_state is HTTPConnectionState.CONNECTED:
            parse_headers(data, protocol=self)
            print(self.headers)
        elif self.connection_state is HTTPConnectionState.HEADERS_RECEIVED:
            self.on_headers_complete()
        elif self.connection_state is HTTPConnectionState.READING_BODY:
            self.on_body(data)

    def on_header(self, header: bytes, value: bytes):
        self.headers.append((header, value))

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
        # print(self.headers)

    def on_body(self, data):
        """Implemented on protocol"""