# asyncio-http-parser

This is an attempt to use the `asyncio.BufferedProtocol` in Python 3.7 as a pure Python/asyncio HTTP request parser. My main intention is to learn more about asyncio protocols and the new features in 3.7 for use in ASGI server development, but I may invest more time into building this out if it seems like it could be useful. I'm developing it with ASGI servers in mind, and it is influenced by the httptools API.

Currently it is able to handle a very simple ASGI hello world application, still much to do.
