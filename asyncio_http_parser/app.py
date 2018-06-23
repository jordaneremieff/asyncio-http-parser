import asyncio


class App:

    def __init__(self, scope):
        self.scope = scope

    async def __call__(self, receive, send):
        message = await receive()
        if message['type'] == 'http.request':
            await send({
                'type': 'http.response.start',
                'status': 200,
                'headers': [
                    # (b"cache-control", b"no-cache"),
                    # (b"content-type", b"text/event-stream"),
                    # (b"transfer-encoding", b"chunked"),
                ]
            })

            body = b"Hello world."  # * 65536
            # max_ = 1
            # for i in range(1, max_ + 1):
            # if i == max_:
            #     more_body = False
            # else:
            #     more_body = True
            print("sending")
            await send({
                'type': 'http.response.body',
                'body': body,
                'more_body': False
            })
            print("sent")
