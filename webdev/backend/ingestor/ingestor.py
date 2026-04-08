from contextlib import asynccontextmanager
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

# Setup a basic logger
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global variables to track throughput
message_count = 0
last_log_time = time.time()
message_length = 0

# Globals for inactivity monitoring
last_message_time = time.time()
is_receiving = False  # True when actively getting a stream of data
GAP_TIMEOUT_SECONDS = 10.0  # How many seconds of silence means "done"


def inactivity_monitor():
    """Runs in the background and watches for gaps in the data stream."""
    global is_receiving, last_message_time

    while True:
        # Check every 1 second
        time.sleep(1.0)

        # If we were receiving data, but the time since the last message exceeds the timeout
        if is_receiving and (time.time() - last_message_time >= GAP_TIMEOUT_SECONDS):
            logger.info(
                f"Stream complete/paused: No messages received for {GAP_TIMEOUT_SECONDS} seconds."
            )

            # Flush any remaining counts/bytes if you want an accurate final tally here
            # (Optional: log the final message_count and message_length here if they didn't hit the 5s mark)

            # Set to False so we don't spam this log. It will reset to True when the next message arrives.
            is_receiving = False


# Callback function for when a message is received
def on_message_received(topic, payload, **kwargs):
    global message_count, last_log_time, message_length
    global last_message_time, is_receiving  # <--- Add the new globals here

    try:
        # --- Activity Tracking (NEW) ---
        last_message_time = time.time()

        # If this is the start of a new stream burst, log it
        if not is_receiving:
            logger.info("New data stream detected. Starting to receive messages...")
            is_receiving = True

        # --- Core Business Logic ---
        sensor_data = payload.decode("utf-8")

        if redis_conn:
            redis_conn.lpush("raw_sensor_data", sensor_data)

        # --- Logging Logic ---
        message_count += 1
        message_length += len(payload)
        current_time = time.time()

        # Only output an INFO log every 5 seconds
        if current_time - last_log_time >= 5.0:
            time_elapsed = current_time - last_log_time
            logger.info(
                f"Health Check: Pushed {message_count} messages to Redis in the last {time_elapsed:.1f} seconds. payload handled per second (MB): {(message_length/1024/1024)/time_elapsed:.2f} MB/s"
            )

            # Reset the counters
            message_count = 0
            message_length = 0
            last_log_time = current_time

    except Exception as e:
        logger.error(
            f"Critical error processing message on topic {topic}: {e}", exc_info=True
        )


@asynccontextmanager
async def lifespan():
    monitor_thread = threading.Thread(target=inactivity_monitor, daemon=True)
    monitor_thread.start()
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
