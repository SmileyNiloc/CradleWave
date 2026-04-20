import redis, os, time, json, logging, multiprocessing
import numpy as np
import humanize, queue

from helpers.DopplerAlgo import DopplerAlgo  # For better logging of data sizes
from helpers.SignalProcessor import SignalProcessor

# Setup a basic logger
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def logging_monitor(
    shutdown_flag,
    log_lock,
    process_data_count,
    process_data_length,
    frames_processed_count,
    processed_data_pushed_count,
):
    """Runs in the background and wakes every 5 seconds to log the current throughput."""

    last_log_time = time.time()
    health_check_idle_count = 0

    # FIX: Exit loop gracefully if shutdown is triggered
    while not shutdown_flag.is_set():
        shutdown_flag.wait(timeout=5)

        current_time = time.time()
        time_elapsed = current_time - last_log_time

        with log_lock:
            # Check if any part of the pipeline had activity
            if (
                process_data_count.value > 0
                or frames_processed_count.value > 0
                or processed_data_pushed_count.value > 0
            ):
                # Calculate MB/s, guarding against division by zero
                bytes_per_sec = (
                    (process_data_length.value) / time_elapsed
                    if time_elapsed > 0
                    else 0
                )

                logger.info(
                    f"Throughput ({time_elapsed:.1f}s): "
                    f"Ingested {process_data_count.value} msgs ({humanize.naturalsize(bytes_per_sec)}/s) | "
                    f"Processed {frames_processed_count.value} queued frames | "
                    f"Pushed {processed_data_pushed_count.value} outputs to Redis out-queue."
                )

                # Reset the counters
                process_data_count.value = 0
                process_data_length.value = 0
                frames_processed_count.value = 0
                processed_data_pushed_count.value = 0
                health_check_idle_count = 0
            elif health_check_idle_count < 3:  # Limit idle logs to avoid spamming
                # OPTIONAL FIX: Give a heartbeat even when idle so you know the thread is alive
                logger.info("Health Check: System idle. 0 messages processed.")
                health_check_idle_count += 1

            # FIX: Unconditionally reset the timer so math is accurate for the next window
            last_log_time = current_time


# Linear to DB
def linear_to_dB(x):
    """Converts a linear value to decibels (dB).
    Args:        x (float): The linear value to convert. Must be non-negative.
    Returns:        float: The corresponding value in decibels (dB). Returns -inf for x=0.
    Raises:        ValueError: If x is negative."""
    # Change this to use small epsilom to avoid log(0)
    return 20 * np.log10(abs(x) + 1e-10)  # avoids log(0)


# 2. Define the background worker function
def process_data(data_points, doppler):

    # PROCESS IT BABY!!!

    # Cast to a numpy array and reshape to (num_chirps_per_frame, num_samples)
    data_2d = np.array(data_points).reshape(32, 64)

    dfft_dbfs = linear_to_dB(doppler.compute_doppler_map(data_2d, 0))
    all_frame_dB_values = dfft_dbfs.flatten()

    if len(all_frame_dB_values) >= 10:
        top_10_values = np.partition(all_frame_dB_values, -10)[-10:]
        frame_peak_dB = np.mean(top_10_values)
    else:
        frame_peak_dB = np.max(all_frame_dB_values)

    # So now we just have 1 peakDB from all that?
    return frame_peak_dB * (-1)


def frame_processor(
    redis_host,
    redis_port,
    raw_signal_queue,
    shutdown_flag,
    log_lock,
    process_data_count,
    process_data_length,
):
    """Main function to connect to Redis and process incoming data."""
    try:
        r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
    except redis.ConnectionError as e:
        logger.critical(f"Could not connect to Redis on startup: {e}")
        exit(1)

    # Define the doppler algorithm parameters
    num_chirps = 32
    num_samples = 64
    num_antennas = 1

    doppler = DopplerAlgo(
        num_samples=num_samples, num_chirps_per_frame=num_chirps, num_ant=num_antennas
    )

    while not shutdown_flag.is_set():
        try:
            # Use a small timeout instead of 0 (infinite) so the loop can check the
            # shutdown_flag periodically if no data is coming in.
            redis_result = r.blpop("raw_sensor_data", timeout=2)
            if not redis_result:
                continue  # Timeout hit, loop back and check shutdown_flag
            queue_name, msg = redis_result
            msg_dict = json.loads(msg)
            data = process_data(msg_dict.get("data", []), doppler)
            raw_signal_queue.put(
                {"data": data, "timestamp": msg_dict.get("timestamp")}
            )  # Send data to the processing thread
            with log_lock:
                process_data_count.value += 1
                process_data_length.value += len(msg.encode("utf-8"))
        except redis.ConnectionError as e:
            logger.error(f"Redis connection error: {e}")
            time.sleep(2)  # Back off and let Redis recover
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            time.sleep(1)


def signal_processor(
    redis_host,
    redis_port,
    raw_signal_queue,
    shutdown_flag,
    log_lock,
    frames_processed_count,
    processed_data_pushed_count,
):
    """Consumes processed signal data from the queue, does further processing if needed, and then pushes results back to Redis."""
    # Connect to Redis
    try:
        r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
    except redis.ConnectionError as e:
        logger.critical(f"Could not connect to Redis on startup: {e}")
        exit(1)

    processor = SignalProcessor(sample_rate=15)
    # There should be 150 values within the raw signal buffer, which corresponds to 10 seconds of data at 15 fps
    raw_signal_np = np.zeros(
        150
    )  # Initialize an empty array to hold the raw signal data

    logger.info("Signal processor started. Waiting for raw signal queue items...")

    # Take data from the queue and do further processing if needed.
    while not shutdown_flag.is_set():
        try:
            data = raw_signal_queue.get(timeout=1)  # Wait for data with timeout

            with log_lock:
                frames_processed_count.value += 1

            # Manually shift the raw_signal_np and append the new data to the end
            raw_signal_np[:-1] = raw_signal_np[1:]  # Shift left by one
            raw_signal_np[-1] = data["data"]  # Append new data at the end
            result = processor.process_signal_pipeline(raw_signal_np)
            export = {
                "timestamp": data["timestamp"],
                "heart_rate": result["heart_rate"],
                "breathing_rate": result["breathing_rate"],
            }

            r.lpush(
                "processed_data", json.dumps(export)
            )  # Push the processed result back to Redis

            with log_lock:
                processed_data_pushed_count.value += 1

            logger.debug(f"Pushed processed data to Redis 'processed_data': {export}")

        except queue.Empty:
            time.sleep(1)  # No data, just wait a bit and check shutdown_flag again
            continue  # No data, loop back and check shutdown_flag


# 4. The Producer (Main Thread) listening to Redis
if __name__ == "__main__":
    redis_host = os.environ.get("REDIS_HOST", "127.0.0.1")
    redis_port = 6379

    # Best practice: Add a health check on startup to ensure Redis is actually there
    print(f"Connecting to Redis on {redis_host}:{redis_port}...")
    try:
        r_check = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        r_check.ping()
        r_check.close()
    except redis.ConnectionError as e:
        logger.critical(f"Could not connect to Redis on startup: {e}")
        exit(1)

    print("Listening for incoming tasks...")

    shutdown_flag = multiprocessing.Event()
    log_lock = multiprocessing.Lock()
    process_data_count = multiprocessing.Value("i", 0)
    process_data_length = multiprocessing.Value("i", 0)

    # New metrics for the signal_processor stage
    frames_processed_count = multiprocessing.Value("i", 0)
    processed_data_pushed_count = multiprocessing.Value("i", 0)

    # Implement a queue for handling data between threads
    raw_signal_queue = multiprocessing.Queue()

    # FIX: Daemon thread is safer here, but we will still cleanly shut it down
    monitor_thread = multiprocessing.Process(
        target=logging_monitor,
        args=(
            shutdown_flag,
            log_lock,
            process_data_count,
            process_data_length,
            frames_processed_count,
            processed_data_pushed_count,
        ),
        daemon=True,
    )
    monitor_thread.start()

    # Thread for processing all the data from Redis.
    # Must give it the redis connection.
    frame_thread = multiprocessing.Process(
        target=frame_processor,
        args=(
            redis_host,
            redis_port,
            raw_signal_queue,
            shutdown_flag,
            log_lock,
            process_data_count,
            process_data_length,
        ),
    )
    frame_thread.start()

    # Thread for processing the raw signal
    signal_thread = multiprocessing.Process(
        target=signal_processor,
        args=(
            redis_host,
            redis_port,
            raw_signal_queue,
            shutdown_flag,
            log_lock,
            frames_processed_count,
            processed_data_pushed_count,
        ),
        daemon=True,
    )
    signal_thread.start()

    try:
        # FIX: Check the shutdown flag instead of 'while True'
        while not shutdown_flag.is_set():
            time.sleep(1)  # Main thread can do other work or just sleep

    except KeyboardInterrupt:
        # FIX: Catch Ctrl+C and shut down cleanly
        logger.info("Shutdown signal received (Ctrl+C). Terminating gracefully...")
        shutdown_flag.set()
    finally:
        logger.info("Waiting for workers to finish current tasks...")
        monitor_thread.join(timeout=2)
        frame_thread.join(timeout=3)
        signal_thread.join(timeout=3)
        logger.info("Processor shut down complete.")
