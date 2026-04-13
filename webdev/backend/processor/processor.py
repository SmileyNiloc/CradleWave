import redis, os, time, json, logging, threading

# Setup a basic logger
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

shutdown_flag = threading.Event()
log_lock = threading.Lock()
process_data_count = 0
process_data_length = 0


def logging_monitor():
    """Runs in the background and wakes every 5 seconds to log the current throughput."""
    global process_data_count, process_data_length

    last_log_time = time.time()

    # FIX: Exit loop gracefully if shutdown is triggered
    while not shutdown_flag.is_set():
        shutdown_flag.wait(timeout=5)

        current_time = time.time()
        time_elapsed = current_time - last_log_time

        with log_lock:
            if process_data_count > 0:
                # Calculate MB/s, guarding against division by zero
                mb_per_sec = (
                    (process_data_length / 1024 / 1024) / time_elapsed
                    if time_elapsed > 0
                    else 0
                )

                logger.info(
                    f"Health Check: Pushed {process_data_count} messages to Redis in the last {time_elapsed:.1f} seconds. "
                    f"Payload handled per second: {mb_per_sec:.2f} MB/s"
                )

                # Reset the counters
                process_data_count = 0
                process_data_length = 0
            else:
                # OPTIONAL FIX: Give a heartbeat even when idle so you know the thread is alive
                logger.info("Health Check: System idle. 0 messages processed.")

            # FIX: Unconditionally reset the timer so math is accurate for the next window
            last_log_time = current_time


# 2. Define the background worker function
def process_data(data_points, timestamp):
    global process_data_count, process_data_length
    # Test calculation:
    avg = sum(data_points) / len(data_points)
    heart_rate = avg
    breathing_rate = avg / 4

    # Send the heart rate, breathing rate, and timestamp to redis to be exported.
    result = {
        "timestamp": timestamp,
        "heart_rate": heart_rate,
        "breathing_rate": breathing_rate,
    }
    r.lpush("processed_data", json.dumps(result))
    with log_lock:
        process_data_count += 1
        process_data_length += len(json.dumps(result))


# 4. The Producer (Main Thread) listening to Redis
print("Connecting to Redis...")
redis_host = os.environ.get("REDIS_HOST", "127.0.0.1")
r = redis.Redis(host=redis_host, port=6379, decode_responses=True)

print("Listening for incoming tasks...")
messages_processed = 0

monitor_thread = threading.Thread(target=logging_monitor, daemon=False)
monitor_thread.start()
while True:
    try:
        # Blocks instantly until Redis gets a new item
        # queue_name is the Redis key, item is the actual payload
        queue_name, msg = r.blpop("raw_sensor_data", 0)

        # Depackage the data from sensor stream (if needed)
        # Should be an array of float 32s

        msg_dict = json.loads(msg)
        # Instantly hand off to the internal Python queue and go right back to listening
        # Float32 array is stored in msg)dict["data"]
        process_data(msg_dict["data"], msg_dict["timestamp"])
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        time.sleep(1)  # Back off on error
