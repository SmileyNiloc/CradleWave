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
    shared_state,
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
                shared_state["process_data_count"] > 0
                or shared_state["frames_processed_count"] > 0
                or shared_state["processed_data_pushed_count"] > 0
            ):
                # Calculate MB/s, guarding against division by zero
                bytes_per_sec = (
                    shared_state["process_data_length"] / time_elapsed
                    if time_elapsed > 0
                    else 0
                )

                logger.info(
                    f"Throughput ({time_elapsed:.1f}s): "
                    f"Ingested {shared_state['process_data_count']} msgs ({humanize.naturalsize(bytes_per_sec)}/s) | "
                    f"Processed {shared_state['frames_processed_count']} queued frames | "
                    f"Pushed {shared_state['processed_data_pushed_count']} outputs to Redis out-queue.\n"
                    f"    Sample -> Frame Max: {shared_state.get('ingested_frame', 'N/A')} | Scalar: {shared_state.get('processed_scalar', 'N/A')} | Pushed: {shared_state.get('pushed_output', 'None')}"
                )

                # Reset the counters and clear samples
                shared_state["process_data_count"] = 0
                shared_state["process_data_length"] = 0
                shared_state["frames_processed_count"] = 0
                shared_state["processed_data_pushed_count"] = 0
                health_check_idle_count = 0

                shared_state["pushed_output"] = None
            elif health_check_idle_count < 3:  # Limit idle logs to avoid spamming
                # OPTIONAL FIX: Give a heartbeat even when idle so you know the thread is alive
                logger.info("Health Check: System idle. 0 messages processed.")
                health_check_idle_count += 1

            # FIX: Unconditionally reset the timer so math is accurate for the next window
            last_log_time = current_time


# ==============================
# Doppler processing
# ==============================


# Input Raw Data Frame -> Output Doppler Map
def doppler_map(frame):
    """Takes a 2D frame of raw radar data and computes the Doppler map using a 2D FFT."""
    if frame.ndim == 1:
        # Assuming 2048 elements: shape into 32 chirps x 64 samples
        frame = frame.reshape(32, 64)

    # Remove DC Offset and Normalize
    frame_float = frame.astype(float)

    # Subtract the mean (average of the frame) to center precisely around zero
    frame_centered = frame_float - np.mean(frame_float)

    # Normalize by dividing by the 12-bit ADC max value (4096) to scale between 0 and 1
    frame_normalized = frame_centered / 4096.0

    # 2D Fast Fourier Transform
    rd = np.fft.fft2(frame_normalized)
    # Shift FFT to order negative -> positive frquencies, zero frequency centered
    rd = np.fft.fftshift(rd, axes=0)
    # Convert to dB
    return 20 * np.log10(np.abs(rd) + 1e-10)


# Input Doppler Raw Data Frame -> Output Scalar (Integration)
def frame_to_scalar(frame):
    # Compute Doppler Map of Raw Data Frame
    rd_map = doppler_map(frame)
    # Flatten 2D Doppler Map to 1D
    frame1D = rd_map.flatten()

    # Should always be true (len = 2048), but prevents error
    if len(frame1D) >= 15:
        # Integration:
        # Select 7 higest energy samples from frame
        integratedFrame = np.partition(frame1D, -7)[-7:]
        # Average 7 highest energy samples to 1 scalar
        scalar = np.mean(integratedFrame)
    else:
        # Extract highest sample
        scalar = np.max(frame1D)

    return -scalar  # Invert sign - doppler values record negative


def frame_processor(
    redis_host,
    redis_port,
    raw_signal_queue,
    shutdown_flag,
    log_lock,
    shared_state,
):
    """Main function to connect to Redis and process incoming data."""
    try:
        r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
    except redis.ConnectionError as e:
        logger.critical(f"Could not connect to Redis on startup: {e}")
        exit(1)

    while not shutdown_flag.is_set():
        try:
            # Use a small timeout instead of 0 (infinite) so the loop can check the
            # shutdown_flag periodically if no data is coming in.
            redis_result = r.blpop("raw_sensor_data", timeout=2)
            if not redis_result:
                continue  # Timeout hit, loop back and check shutdown_flag
            queue_name, msg = redis_result
            msg_dict = json.loads(msg)
            frame = np.array(msg_dict.get("data", [])).reshape(
                32, 64
            )  # Reshape to 2D if needed
            if frame.shape != (32, 64):
                logger.warning(
                    f"Unexpected frame shape: {frame.shape}. Expected (32, 64). Skipping this frame."
                )
                continue
            data = frame_to_scalar(frame)
            raw_signal_queue.put(
                {"data": data, "timestamp": msg_dict.get("timestamp")}
            )  # Send data to the processing thread

            with log_lock:
                shared_state["process_data_count"] += 1
                shared_state["process_data_length"] += len(msg.encode("utf-8"))

                # Periodically sample the data for the logger every 15 frames
                if (
                    shared_state["process_data_count"] == 1
                    or shared_state["process_data_count"] % 15 == 0
                ):
                    shared_state["ingested_frame"] = f"{float(np.max(frame)):.2f}"
                    shared_state["processed_scalar"] = f"{float(data):.2f}"

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
    shared_state,
):
    """Consumes processed signal data from the queue, does further processing if needed, and then pushes results back to Redis."""
    # Connect to Redis
    try:
        r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
    except redis.ConnectionError as e:
        logger.critical(f"Could not connect to Redis on startup: {e}")
        exit(1)

    processor = SignalProcessor(sample_rate=15)

    # 20 seconds of data at 15 fps = 300 values
    buffer_size = 300
    raw_signal_np = np.zeros(buffer_size)

    # Trackers for cold start and inactivity flush
    valid_samples = 0
    samples_since_last_process = 0
    last_frame_time = time.time()

    previous_export = {
        "heart_rate": 0,
        "breathing_rate": 0,
    }  # To hold previous values for continuity

    logger.info("Signal processor started. Waiting for raw signal queue items...")

    # Take data from the queue and do further processing if needed.
    while not shutdown_flag.is_set():
        try:
            data = raw_signal_queue.get(timeout=1)  # Wait for data with timeout

            # Update activity timer
            last_frame_time = time.time()

            with log_lock:
                shared_state["frames_processed_count"] += 1

            # Manually shift the raw_signal_np and append the new data to the end
            raw_signal_np[:-1] = raw_signal_np[1:]  # Shift left by one
            raw_signal_np[-1] = data["data"]  # Append new data at the end

            # Increment our valid sample counter (cap it at the buffer size)
            if valid_samples < buffer_size:
                valid_samples += 1

            # Only process and push to Redis if we have a fully saturated buffer
            # Then reset the buffer to 10 seconds of data (150 samples) to create a sliding window effect, and keep the last 150 samples for continuity
            if valid_samples >= buffer_size:
                result = processor.process_signal_pipeline(
                    raw_signal_np,
                    prev_heart_val=previous_export["heart_rate"],
                    prev_breath_val=previous_export["breathing_rate"],
                )
                export = {
                    "timestamp": data["timestamp"],
                    "heart_rate": (
                        result["heart_rate_bpm"][0][1]
                        if result["heart_rate_bpm"]
                        else previous_export["heart_rate"]
                    ),
                    "breathing_rate": (
                        result["breathing_rate"][0][1]
                        if result["breathing_rate"]
                        else previous_export["breathing_rate"]
                    ),
                    "filtered_heart": (
                        (
                            result["filtered_heart"][0][1]
                            if result["filtered_heart"]
                            else previous_export["filtered_heart"]
                        ),
                    ),
                    "filtered_breathing": (
                        (
                            result["filtered_breathing"][0][1]
                            if result["filtered_breathing"]
                            else previous_export["filtered_breathing"]
                        ),
                    ),
                }
                previous_export = (
                    export  # Update previous values for the next iteration
                )
                r.lpush(
                    "processed_data", json.dumps(export)
                )  # Push the processed result back to Redis

                with log_lock:
                    shared_state["processed_data_pushed_count"] += 1
                    shared_state["pushed_output"] = (
                        f"HR: {export['heart_rate']:.1f} "
                        f"| BR: {export['breathing_rate']:.1f}"
                    )

                logger.debug(
                    f"Pushed processed data to Redis 'processed_data': {export}"
                )
                valid_samples = 0  # Reset to 10 seconds of data (150 samples) for sliding window effect
            else:
                # Optional: Log the cold start progress
                logger.debug(
                    f"Buffering raw signal data... ({valid_samples}/{buffer_size})"
                )

        except queue.Empty:
            # If the queue is empty, check if we've been inactive for more than 5 seconds
            # The 'valid_samples > 0' check ensures we only flush once per inactive period
            if valid_samples > 0 and (time.time() - last_frame_time) > 5.0:
                logger.info("No data received for 5 seconds. Flushing signal buffer.")
                raw_signal_np = np.zeros(buffer_size)
                valid_samples = 0

            # Note: Removed time.sleep(1) here because queue.get(timeout=1) already provides a 1-second delay
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

    # Use a multiprocessing dict to share ALL state across processes
    manager = multiprocessing.Manager()
    shared_state = manager.dict()

    # Initialize metrics
    shared_state["process_data_count"] = 0
    shared_state["process_data_length"] = 0
    shared_state["frames_processed_count"] = 0
    shared_state["processed_data_pushed_count"] = 0

    # Initialize samples
    shared_state["ingested_frame"] = "None"
    shared_state["processed_scalar"] = "None"
    shared_state["pushed_output"] = "None"

    # Implement a queue for handling data between threads
    raw_signal_queue = multiprocessing.Queue()

    # FIX: Daemon thread is safer here, but we will still cleanly shut it down
    monitor_thread = multiprocessing.Process(
        target=logging_monitor,
        args=(
            shutdown_flag,
            log_lock,
            shared_state,
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
            shared_state,
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
            shared_state,
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
