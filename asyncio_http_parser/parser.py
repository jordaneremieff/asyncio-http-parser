import enum
import logging
import asyncio
from typing import List, Tuple
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
                print(_header)
                request_info.set(_header)
                # 'GET / HTTP/1.1\r\n'
                request_headers.set([])
                parsing_data.set(_parsing_data[_pos:])
                _request_headers = request_headers.get()
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
    RECEIVING = 1
    WRITE_PAUSED = 2
    READ_PAUSED = 3


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
        print(data)
        print(self.request_state)

        if self.request_state is HTTPRequestState.CONNECTING:

            set_header(data)
            # print(data)
            _parsing_ended = parsing_ended.get()

            if _parsing_ended:
                self.state = HTTPRequestState.RECEIVING
                self.request_headers = request_headers.get()
                self.request_info = request_info.get()

                self.on_headers_complete()

        if self.request_state is HTTPRequestState.RECEIVING:
            print("Receiving")
            self.on_body(data)

    async def drain(self) -> None:
        await self.drain_waiter.wait()

    def pause_writing(self) -> None:
        assert not self.write_paused, "Invalid write state"
        self.write_paused = True
        self.drain_waiter.clear()

    def resume_writing(self) -> None:
        assert self.write_paused, "Invalid write state"
        self.write_paused = False
        self.drain_waiter.set()

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
                print(header)
            else:
                end = len(header) - 2
                header = [header[:sep], header[sep + 2:end]]
                headers.append(header)
        return headers

    # def get_http_version(self) -> str:

    # def should_keep_alive(self) -> bool:

    # def should_upgrade(self) -> bool:

    # def get_method(self) -> bytes:
