from asyncio import Queue, create_task, sleep as io_sleep
import websockets
import msgpack

class WebSocketClient:
    def __initi__(self,url):
        self.url = url
        self.websocket = None
        self.queue = Queue()

    async def connect(self):
        """Establish a WebSocket connection (and keep open)."""
        while not self.websocket:
            try:
                self.websocket = await websockets.connect(self.url, compression=None)
                create_task(self._send_loop())
            except Exception as e:
                print(f"Connection failed: {e}. Retrying in 5 seconds...")
                await io_sleep(5)
    async def send_data(self,data):
        """Queue data to be sent over the WebSocket."""
        await self.queue.put(data)

    async def _send_loop(self):
        """Continuously send data from the queue over the WebSocket."""
        while True:
            if self.websocket:
                try:
                    # Get data from the queue
                    data = await self.queue.get()
                    # package into binary (for efficiency) and send the data
                    packed_data = msgpack.packb(data)
                    await self.websocket.send(packed_data)
                    # Mark the task as done
                    self.queue.task_done()
                except Exception as e:
                    print(f"Error sending data: {e}")