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
    health_check_idle_count = 0

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
                    f"Payload handled per second: {mb_per_sec:.4f} MB/s"
                )

                # Reset the counters
                process_data_count = 0
                process_data_length = 0
                health_check_idle_count = 0
            elif health_check_idle_count < 3:  # Limit idle logs to avoid spamming
                # OPTIONAL FIX: Give a heartbeat even when idle so you know the thread is alive
                logger.info("Health Check: System idle. 0 messages processed.")
                health_check_idle_count += 1

            # FIX: Unconditionally reset the timer so math is accurate for the next window
            last_log_time = current_time


# 2. Define the background worker function
def process_data(r, data_points, timestamp):
    # FIX: Guard against division by zero
    if not data_points:
        logger.warning(
            f"Empty data array received for timestamp {timestamp}. Skipping."
        )
        return

    global process_data_count, process_data_length

    avg = sum(data_points) / len(data_points)
    heart_rate = avg
    breathing_rate = avg / 4

    result = {
        "timestamp": timestamp,
        "heart_rate": heart_rate,
        "breathing_rate": breathing_rate,
    }

    # FIX: Serialize only once
    json_payload = json.dumps(result)

    r.lpush("processed_data", json_payload)

    with log_lock:
        process_data_count += 1
        process_data_length += len(json_payload.encode("utf-8"))


# 4. The Producer (Main Thread) listening to Redis
if __name__ == "__main__":
    print("Connecting to Redis...")
    redis_host = os.environ.get("REDIS_HOST", "127.0.0.1")

    # Best practice: Add a health check on startup to ensure Redis is actually there
    try:
        r = redis.Redis(
            host=redis_host, port=6379, decode_responses=True, socket_timeout=5
        )
        r.ping()
        # Remove the global socket timeout after pinging so blpop can block indefinitely
        r = redis.Redis(host=redis_host, port=6379, decode_responses=True)
    except redis.ConnectionError as e:
        logger.critical(f"Could not connect to Redis on startup: {e}")
        exit(1)

    print("Listening for incoming tasks...")

    # FIX: Daemon thread is safer here, but we will still cleanly shut it down
    monitor_thread = threading.Thread(target=logging_monitor, daemon=True)
    monitor_thread.start()

    try:
        # FIX: Check the shutdown flag instead of 'while True'
        while not shutdown_flag.is_set():
            try:
                # Use a small timeout instead of 0 (infinite) so the loop can check the
                # shutdown_flag periodically if no data is coming in.
                redis_result = r.blpop("raw_sensor_data", timeout=2)

                if not redis_result:
                    continue  # Timeout hit, loop back and check shutdown_flag

                queue_name, msg = redis_result
                msg_dict = json.loads(msg)

                process_data(r, msg_dict.get("data", []), msg_dict.get("timestamp"))

            except redis.ConnectionError as e:
                logger.error(f"Redis connection error: {e}")
                time.sleep(2)  # Back off and let Redis recover
            except Exception as e:
                logger.error(f"Error processing message: {e}", exc_info=True)
                time.sleep(1)

    except KeyboardInterrupt:
        # FIX: Catch Ctrl+C and shut down cleanly
        logger.info("Shutdown signal received (Ctrl+C). Terminating gracefully...")
        shutdown_flag.set()
    finally:
        # Wait a moment for the monitor thread to output its final log
        monitor_thread.join(timeout=2)
        logger.info("Processor shut down complete.")
