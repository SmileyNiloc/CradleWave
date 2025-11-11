from asyncio import Queue, create_task, sleep as io_sleep
import websockets
import msgpack
import numpy as np
import time
import datetime, secrets

class WebSocketClient:
    def __init__(self, url):
        self.url = url
        self.websocket = None
        self.queue = Queue()
        self.connected = False
        self.total_sent = 0
        self.session_id = self.generate_session_id()
        print(f"[WebSocket] Initialized with URL: {url}")

    async def connect(self):
        """Establish a WebSocket connection (and keep open)."""
        print(f"[WebSocket] Attempting to connect to {self.url}...")
        retry_count = 0
        
        while not self.websocket:
            try:
                print(f"[WebSocket] Connection attempt #{retry_count + 1}")
                self.websocket = await websockets.connect(self.url, compression=None)
                self.connected = True
                print(f"[WebSocket] ✓ Successfully connected!")
                print(f"[WebSocket] Starting send loop...")
                create_task(self._send_loop())
                break
            except Exception as e:
                retry_count += 1
                print(f"[WebSocket] ✗ Connection failed (attempt #{retry_count}): {e}")
                print(f"[WebSocket] Retrying in 5 seconds...")
                await io_sleep(5)
    
    async def send_data(self, data):
        """Queue data to be sent over the WebSocket."""
        queue_size = self.queue.qsize()
        print(f"[WebSocket] Queueing data (queue size: {queue_size})")
        await self.queue.put(data)
        print(f"[WebSocket] Data queued successfully")

    async def _send_loop(self):
        """Continuously send data from the queue over the WebSocket."""
        print(f"[WebSocket] Send loop started")
        
        while True:
            if self.websocket:
                try:
                    # Get data from the queue
                    print(f"[WebSocket] Waiting for data from queue...")
                    data = await self.queue.get()
                    print(f"[WebSocket] Got data from queue: {type(data)}")

                    #Make data JSON safe
                    safe_data = self.make_json_safe(data)

                    #Add Metadata
                    structure = {
                        "user": "demo_board",
                        "session_id": self.session_id,
                        "timestamp": time.time(),
                        "data": safe_data,

                    }

                    # Pack data using msgpack
                    packed_data = msgpack.packb(structure)

                    data_size = len(packed_data)
                    print(f"[WebSocket] Packed data size: {data_size} bytes")
                    
                    await self.websocket.send(packed_data)
                    self.total_sent += 1
                    print(f"[WebSocket] ✓ Data sent successfully (total sent: {self.total_sent})")
                    
                    # Mark the task as done
                    self.queue.task_done()
                    print(f"[WebSocket] Queue task marked as done")
                    
                except websockets.exceptions.ConnectionClosed as e:
                    print(f"[WebSocket] ✗ Connection closed: {e}")
                    print(f"[WebSocket] Reconnecting...")
                    self.websocket = None
                    self.connected = False
                    await self.connect()
                except Exception as e:
                    print(f"[WebSocket] ✗ Error sending data: {e}")
                    print(f"[WebSocket] Error type: {type(e).__name__}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"[WebSocket] No active connection, waiting...")
                await io_sleep(1)
    async def wait_until_done(self):
        """Wait until all queued data has been sent."""
        await self.queue.join() 
        print(f"[WebSocket] All queued data has been sent")

    def make_json_safe(self, obj):
        """Convert numpy arrays and scalars to plain Python types."""
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (np.generic,)):  # handles np.float32, np.int64, etc.
            return obj.item()
        elif isinstance(obj, dict):
            return {k: self.make_json_safe(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.make_json_safe(v) for v in obj]
        else:
            return obj

    def generate_session_id(self, prefix="session"):
        now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        rand = secrets.token_hex(3)  # 6 hex chars (~1M combinations)
        return f"{prefix}_{now}_{rand}"