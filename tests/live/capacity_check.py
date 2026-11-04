"""With every place taken, the next caller must be told so rather than left waiting.
Needs the running server. Run from the project folder."""
import asyncio
import json
import sys

import websockets

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf8")
from tests.live.client import Client, start_conversation

URL = "ws://localhost:8000/ws/voice"


async def main() -> None:
    first = start_conversation("healthcare", "en")
    second = start_conversation("healthcare", "hi")
    third = start_conversation("healthcare", "bn")
    async with Client(first), Client(second):
        async with websockets.connect(URL, origin="http://localhost:8000") as socket:
            await socket.send(json.dumps({"type": "start", "id": third["id"], "token": third["token"], "mode": "voice"}))
            try:
                while True:
                    print("third caller got", str(await asyncio.wait_for(socket.recv(), 10))[:200])
            except websockets.ConnectionClosed as closed:
                print("third caller closed with", closed.code, closed.reason)
                assert closed.code == 4503
    await asyncio.sleep(1)
    async with Client(third) as caller:
        answer = await caller.ask_text("পার্কিং আছে কি?")
        print("place free again, third caller got:", answer.text[:80])
        assert answer.text
    print("capacity check passed")


asyncio.run(main())
