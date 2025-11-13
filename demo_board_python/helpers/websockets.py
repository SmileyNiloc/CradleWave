from asyncio import Queue, create_task, sleep as io_sleep
import websockets
import msgpack
import numpy as np
import time
import datetime, secrets


class WebSocketClient:
    """
    Asynchronous WebSocket client for streaming sensor data.

    This client manages a persistent WebSocket connection with automatic reconnection,
    message queueing, and msgpack serialization. It's designed for real-time streaming
    of radar sensor data from the demo board to a remote server.

    Attributes:
        url (str): WebSocket server URL (e.g., 'wss://example.com/ws/data')
        websocket: Active WebSocket connection object or None
        queue (asyncio.Queue): Thread-safe queue for outgoing messages
        connected (bool): Current connection status
        total_sent (int): Counter for successfully transmitted messages
        session_id (str): Unique session identifier for this client instance

    Example:
        >>> client = WebSocketClient('wss://example.com/ws/data')
        >>> await client.connect()
        >>> await client.send_data({'heart_rate': 72})
        >>> await client.wait_until_done()
    Note:
        - USE asyncio.sleep or something else with asyncio to make sure that the background process of sending data actually happens
        - Designed for use with asyncio event loop
    """

    def __init__(self, url):
        """
        Initialize the WebSocket client.

        Args:
            url (str): WebSocket server URL. Must use 'ws://' or 'wss://' scheme.
                      Example: 'wss://cradlewave.example.com/ws/filtered'

        Note:
            Connection is not established until connect() is called.
        """
        self.url = url
        self.websocket = None
        self.queue = Queue()
        self.connected = False
        self.total_sent = 0
        self.session_id = self.generate_session_id()
        print(f"[WebSocket] Initialized with URL: {url}")

    async def connect(self):
        """
        Establish and maintain a WebSocket connection with automatic retry.

        This method attempts to connect to the WebSocket server and will retry
        indefinitely with a 5-second delay between attempts. Once connected,
        it automatically starts the background send loop.

        The connection remains open until explicitly closed or until an error occurs,
        at which point automatic reconnection is attempted.

        Raises:
            Exception: Logs connection errors but continues retrying indefinitely.

        Note:
            This is a blocking call until the first successful connection.
            Subsequent reconnections happen automatically in the background.
        """
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
        """
        Queue data for transmission over the WebSocket.

        Data is added to an internal queue and sent asynchronously by the background
        send loop. This method returns immediately without blocking, making it safe
        to call from real-time data processing loops.

        The data will be automatically serialized to msgpack format with metadata
        including device ID, session ID, and timestamp.

        Args:
            data (dict|must be JSON style array:
                { "key that is under sessionId": value}
        Note:7 a910p
            - Data is queued, not sent immediately
            - Use wait_until_done() to block until queue is empty
            - Queue has no size limit; beware of memory usage with fast producers

        Example:
            >>> await client.send_data({'filtered_signal': [1.2, 3.4, 5.6]})
            >>> await client.send_data({'bpm': 72, 'confidence': 0.95})
        """
        queue_size = self.queue.qsize()
        print(f"[WebSocket] Queueing data (queue size: {queue_size})")
        await self.queue.put(data)
        print(f"[WebSocket] Data queued successfully")

    async def _send_loop(self):
        """
        Background task that continuously processes and sends queued data.

        This coroutine runs in the background and:
        1. Retrieves data from the queue
        2. Wraps it with metadata (device ID, session ID, timestamp)
        3. Serializes to msgpack binary format
        4. Transmits over the WebSocket
        5. Handles reconnection on connection loss

        This method is automatically started by connect() and should not be
        called directly.

        The loop runs indefinitely and will:
        - Wait for queue items when queue is empty
        - Reconnect automatically if connection drops
        - Log all transmission events and errors

        Raises:
            Exception: All exceptions are caught, logged, and handled gracefully.
        """
        print(f"[WebSocket] Send loop started")

        while True:
            if self.websocket:
                try:
                    # Get data from the queue
                    print(f"[WebSocket] Waiting for data from queue...")
                    data = await self.queue.get()
                    print(f"[WebSocket] Got data from queue: {type(data)}")

                    # Make data JSON safe
                    safe_data = self.make_json_safe(data)

                    # Add Metadata
                    structure = {
                        "device": "demo_board",
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
                    print(
                        f"[WebSocket] ✓ Data sent successfully (total sent: {self.total_sent})"
                    )

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
        """
        Block until all queued data has been transmitted.

        This method waits for the internal queue to be empty, ensuring all
        previously queued data has been sent over the WebSocket. Useful for
        ensuring data is transmitted before shutting down or transitioning
        between phases.

        Note:
            - This does not guarantee server receipt, only that data was sent
            - Will block indefinitely if send loop encounters persistent errors
            - Queue is considered "done" when all items have been processed

        Example:
            >>> await client.send_data(data1)
            >>> await client.send_data(data2)
            >>> await client.wait_until_done()  # Blocks until both sent
            >>> print("All data transmitted!")
        """
        await self.queue.join()
        print(f"[WebSocket] All queued data has been sent")

    def make_json_safe(self, obj):
        """
        Recursively convert numpy types to native Python types for serialization.

        This method ensures data can be safely serialized to msgpack/JSON by
        converting:
        - numpy arrays to Python lists
        - numpy scalars (np.float32, np.int64, etc.) to Python scalars
        - Recursively processes nested dictionaries and lists

        Args:
            obj: Object to convert. Can be any combination of:
                - numpy arrays and scalars
                - dicts, lists, tuples
                - native Python types (returned unchanged)

        Returns:
            Object with all numpy types converted to native Python types.
            Structure is preserved (dicts remain dicts, lists remain lists).

        Example:
            >>> data = {'signal': np.array([1.0, 2.0]), 'value': np.float32(3.5)}
            >>> safe = client.make_json_safe(data)
            >>> # safe = {'signal': [1.0, 2.0], 'value': 3.5}
        """
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
        """
        Generate a unique session identifier with timestamp.

        Creates a session ID in the format: {prefix}_{YYYYMMDD_HHMMSS}_{random}
        where random is a 6-character hexadecimal string providing ~1 million
        unique combinations per second.

        Args:
            prefix (str, optional): Prefix for the session ID. Defaults to "session".

        Returns:
            str: Unique session identifier (e.g., "session_20251113_143027_a3f4c2")

        Example:
            >>> id1 = client.generate_session_id()
            >>> # "session_20251113_143027_a3f4c2"
            >>> id2 = client.generate_session_id(prefix="radar")
            >>> # "radar_20251113_143027_b7d9e1"
        """
        now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        rand = secrets.token_hex(3)  # 6 hex chars (~1M combinations)
        return f"{prefix}_{now}_{rand}"
