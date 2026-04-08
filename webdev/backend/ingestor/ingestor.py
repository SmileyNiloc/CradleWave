from contextlib import asynccontextmanager
import queue
from awsiot import mqtt_connection_builder  # type: ignore
from awscrt import mqtt  # type: ignore
import json, redis, os, asyncio
import logging, time, threading

# List of origins that are allowed to make requests
origins = [
    # "http://localhost:5047",
    "*"
]

ROOT_CA_PATH = os.environ.get("AWS_ROOT_CA", "./AmazonRootCA1.pem")
PRIVATE_KEY_PATH = os.environ.get("AWS_PRIVATE_KEY", "./private.pem.key")
CERT_PATH = os.environ.get("AWS_CERT", "./certificate.pem.crt")

# Global variables
# hold persistent connection
mqtt_conn = None
# Hold last value (testing)
last_message = None
# Hold Redis connection
redis_conn = None
payload_queue = queue.Queue()

# Setup a basic logger
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global variables to track throughput
message_count = 0
last_log_time = time.time()
message_length = 0
current_time = None


def logging_monitor():
    """Runs in the background and wakes every 5 seconds to log the current throughput."""
    global is_receiving, current_time, message_count, message_length

    while True:
        time.sleep(5.0)

        time_elapsed = current_time - last_log_time
        logger.info(
            f"Health Check: Pushed {message_count} messages to Redis in the last {time_elapsed:.1f} seconds. payload handled per second (MB): {(message_length/1024/1024)/time_elapsed:.2f} MB/s"
        )
        # Reset the counters
        message_count = 0
        message_length = 0
        last_log_time = current_time


# Callback function for when a message is received
def on_message_received(topic, payload, **kwargs):
    global message_count, last_log_time, message_length, current_time

    try:

        current_time = time.time()

        sensor_data = payload.decode("utf-8")
        payload_queue.put(sensor_data)

        # --- Logging Logic ---
        message_count += 1
        message_length += len(payload)

    except Exception as e:
        logger.error(
            f"Critical error processing message on topic {topic}: {e}", exc_info=True
        )


def redis_batch_worker(redis_conn, batch_size=100, flush_interval=1.0):
    """
    periodically flushes the queue into Redis in bulk.
    """
    while True:
        batch = []
        # Collect up to batch_size items
        try:
            # Wait for at least one item to avoid a busy loop
            first_item = payload_queue.get(timeout=flush_interval)
            batch.append(first_item)

            # Grab more items if available, up to batch_size
            while len(batch) < batch_size:
                try:
                    batch.append(payload_queue.get_nowait())
                except queue.Empty:
                    break
        except queue.Empty:
            # No items arrived within flush_interval, loop again
            continue

        if batch:
            try:
                # Use a pipeline for O(1) network trip
                pipe = redis_conn.pipeline()
                for item in batch:
                    # LPUSH for FIFO (paired with RPOP on the consumer side)
                    pipe.lpush("raw_sensor_data", item)
                pipe.execute()

                # Mark queue tasks as done
                for _ in range(len(batch)):
                    payload_queue.task_done()

            except Exception as e:
                logger.error(f"Redis Batch Error: {e}")
                # Optional: Re-queue items or handle retry logic


@asynccontextmanager
async def lifespan():
    monitor_thread = threading.Thread(target=logging_monitor, daemon=True)
    monitor_thread.start()
    worker_thread = threading.Thread(
        target=redis_batch_worker,
        args=(redis_conn,),
        kwargs={"batch_size": 250, "flush_interval": 0.5},
        daemon=True,
    )
    worker_thread.start()
    # --- Startup: Connect to IoT Core ---
    global mqtt_conn
    mqtt_conn = mqtt_connection_builder.mtls_from_path(
        endpoint="a1py3mdrrjrz1-ats.iot.us-east-1.amazonaws.com",
        cert_filepath=CERT_PATH,
        pri_key_filepath=PRIVATE_KEY_PATH,
        ca_filepath=ROOT_CA_PATH,
        client_id="cradlewave-ingestor",  # Ensure this is unique across your fleet
        clean_session=False,
        keep_alive_secs=30,
    )

    print("Connecting to IoT Core...")
    mqtt_conn.connect().result()
    print("Connected!")

    # connect to Redis
    global redis_conn
    redis_host = os.environ.get("REDIS_HOST", "127.0.0.1")
    redis_conn = redis.Redis(host=redis_host, port=6379, decode_responses=True)

    # Subscribe to the MQTT node where the sensor data is published
    subscribe_topic = "raw_sensor_data"

    subscribe_future, packet_id = mqtt_conn.subscribe(
        topic=subscribe_topic,
        qos=mqtt.QoS.AT_LEAST_ONCE,
        callback=on_message_received,
    )
    subscribe_result = subscribe_future.result()
    print(f"Subscribed to {subscribe_topic} with {subscribe_result['qos']} QoS")

    yield  # The app runs here

    # --- Shutdown: Clean up ---
    print("Disconnecting...")
    mqtt_conn.disconnect().result()


async def _run_forever():
    """Run the lifespan and wait until interrupted (Ctrl+C)."""
    try:
        async with lifespan():
            print("Running. Press Ctrl+C to exit.")
            await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(_run_forever())
    except KeyboardInterrupt:
        print("Interrupted — exiting")
