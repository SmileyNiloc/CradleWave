import json

from awsiot import mqtt_connection_builder  # type: ignore
from awscrt import mqtt  # type: ignore
import redis, os, queue, logging, time, threading, struct
import humanize  # For better logging of data sizes

ROOT_CA_PATH = os.environ.get("AWS_ROOT_CA", "./AmazonRootCA1.pem")
PRIVATE_KEY_PATH = os.environ.get("AWS_PRIVATE_KEY", "./private.pem.key")
CERT_PATH = os.environ.get("AWS_CERT", "./certificate.pem.crt")
AWS_ENDPOINT = os.environ.get(
    "AWS_ENDPOINT", "a1py3mdrrjrz1-ats.iot.us-east-1.amazonaws.com"
)


# Global variables
# hold persistent connection
mqtt_conn = None
# Hold Redis connection
redis_conn = None

# Setup a basic logger
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global variables to track throughput
message_lock = threading.Lock()
message_count = 0
message_length = 0

# Global variables for previews
latest_raw_topic = None
latest_raw_payload = None
latest_unpacked_timestamp = None
latest_unpacked_data = None
latest_batch_size = 0
latest_batch_len = 0
latest_batch_preview = None

# Global Threading event to signal shutdown
shutdown_flag = threading.Event()


def logging_monitor():
    """Runs in the background and wakes every 5 seconds to log the current throughput and previews."""
    global message_count, message_length
    global latest_raw_topic, latest_raw_payload, latest_unpacked_timestamp, latest_unpacked_data
    global latest_batch_size, latest_batch_len, latest_batch_preview

    last_log_time = time.time()

    while True:
        shutdown_flag.wait(timeout=5)  # Waits for 5 seconds or until shutdown

        current_time = time.time()
        time_elapsed = current_time - last_log_time
        with message_lock:
            if message_count > 0:
                logger.info(
                    f"Health Check: Received {message_count} messages from AWS in the last {time_elapsed:.1f} seconds. Payload handled per second: {humanize.naturalsize((message_length)/time_elapsed)}/s"
                )

                # Log the MQTT In Preview
                if latest_raw_payload is not None:
                    logger.info(
                        f"MQTT In Preview -> topic='{latest_raw_topic}', raw payload={repr(latest_raw_payload[:50])}... (Total {len(latest_raw_payload)} bytes)"
                    )

                # Log the Unpacked Data Preview
                if latest_unpacked_data is not None:
                    logger.info(
                        f"Unpacked Preview -> timestamp={latest_unpacked_timestamp}, parsed data={latest_unpacked_data}... (Total 2048 elements)"
                    )

                # Log the Redis Export Preview
                if latest_batch_preview is not None:
                    logger.info(
                        f"Redis Export Preview -> Pushed batch of {latest_batch_len} items (Total size: {humanize.naturalsize(latest_batch_size)}). Data: {latest_batch_preview}"
                    )

                # Reset the counters
                message_count = 0
                message_length = 0

            last_log_time = current_time


def unpack_cradlewave(payload_bytes):
    if len(payload_bytes) != 4104:
        raise ValueError(f"Expected 4104 bytes, got {len(payload_bytes)}")

    # Unpack the timestamp using struct as 64-bit uint
    timestamp_ms = struct.unpack("<Q", payload_bytes[:8])[0]

    # Unpack samples directly using struct
    # '<2048H' means 2048 Little-Endian, Unsigned 16-bit integers
    samples_tuple = struct.unpack("<2048H", payload_bytes[8:])

    return timestamp_ms, samples_tuple


# Callback function for when a message is received
def on_message_received(topic, payload, **kwargs):
    global message_count, message_length
    global latest_raw_topic, latest_raw_payload, latest_unpacked_timestamp, latest_unpacked_data

    try:
        timestamp, sensor_data = unpack_cradlewave(payload)

        payload_dict = {"timestamp": timestamp, "data": list(sensor_data)}
        kwargs.get("queue").put(json.dumps(payload_dict))

        with message_lock:
            # --- Logging Logic ---
            message_count += 1
            message_length += len(payload)
            latest_raw_topic = topic
            latest_raw_payload = payload
            latest_unpacked_timestamp = timestamp
            latest_unpacked_data = list(sensor_data[:5])

    except Exception as e:
        logger.error(
            f"Critical error processing message on topic {topic}: {e}", exc_info=True
        )


def redis_batch_worker(redis_conn, ingestion_queue, batch_size=100, flush_interval=1.0):
    """WS_ENDPOINT
    periodically flushes the queue into Redis in bulk.
    """
    global latest_batch_len, latest_batch_size, latest_batch_preview

    while not shutdown_flag.is_set() or not ingestion_queue.empty():
        batch = []
        # Collect up to batch_size items
        try:
            # Wait for at least one item to avoid a busy loop
            first_item = ingestion_queue.get(timeout=flush_interval)
            batch.append(first_item)

            # Grab more items if available, up to batch_size
            while len(batch) < batch_size:
                try:
                    batch.append(ingestion_queue.get_nowait())
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

                with message_lock:
                    latest_batch_len = len(batch)
                    latest_batch_size = sum(len(item) for item in batch)
                    latest_batch_preview = (
                        batch[0][:150] + "... ]}" if len(batch[0]) > 150 else batch[0]
                    )

                # Mark queue tasks as done
                for _ in range(len(batch)):
                    ingestion_queue.task_done()

            except Exception as e:
                logger.error(f"Redis Batch Error: {e}")
                # Optional: Re-queue items or handle retry logic


if __name__ == "__main__":
    payload_queue = queue.Queue()

    monitor_thread = threading.Thread(target=logging_monitor, daemon=True)
    monitor_thread.start()

    # Setup Redis Connection
    redis_conn = None
    redis_host = os.environ.get("REDIS_HOST", "127.0.0.1")
    redis_conn = redis.Redis(host=redis_host, port=6379, decode_responses=True)
    redis_conn.ping()
    logger.info("Connected to Redis successfully.")

    # Setup the worker that will batch received MQTT messages from
    worker_thread = threading.Thread(
        target=redis_batch_worker,
        args=(redis_conn, payload_queue),
        kwargs={"batch_size": 250, "flush_interval": 0.5},
        daemon=False,
    )
    worker_thread.start()

    # --- Startup: Connect to IoT Core ---
    mqtt_conn = None

    mqtt_conn = mqtt_connection_builder.mtls_from_path(
        endpoint=AWS_ENDPOINT,
        cert_filepath=CERT_PATH,
        pri_key_filepath=PRIVATE_KEY_PATH,
        ca_filepath=ROOT_CA_PATH,
        client_id="cradlewave-ingestor",  # Ensure this is unique across your fleet
        clean_session=False,
        keep_alive_secs=30,
    )

    mqtt_conn.connect().result()

    subscribe_topic = "raw_sensor_data"

    # Subscribe with QoS 1 (at least once delivery)
    subscribe_future, packet_id = mqtt_conn.subscribe(
        topic=subscribe_topic,
        qos=mqtt.QoS.AT_LEAST_ONCE,
        callback=lambda topic, payload, dup, qos, retain, **kwargs: on_message_received(
            topic, payload, queue=payload_queue
        ),
    )
    subscribe_result = subscribe_future.result()

    try:
        while not shutdown_flag.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down workers...")
        mqtt_conn.disconnect().result()
        shutdown_flag.set()
        worker_thread.join()  # Waits for the thread to exit cleanly
        logger.info("Worker shutdown complete.")
