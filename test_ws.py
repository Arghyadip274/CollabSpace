import asyncio
import websockets
import sys

async def test_ws():
    uri = 'wss://collabspace-backend-c26l.onrender.com/realtime/ws?token=test'
    try:
        async with websockets.connect(uri) as websocket:
            print('Connected!')
            # Since the token is invalid, the server might disconnect immediately,
            # but we just want to see if the connection is accepted or rejected.
            await websocket.recv()
    except Exception as e:
        print(f'Failed: {e}')

asyncio.get_event_loop().run_until_complete(test_ws())
