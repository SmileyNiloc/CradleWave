import redis, argparse, time, multiprocessing, random, json
import matplotlib.pyplot as plt
from collections import deque


def arguement_parser():
    parser = argparse.ArgumentParser(description="Send test messages to Local Pipeline")
    parser.add_argument(
        "--test-data",
        type=str,
        default=None,
        help="Path to CSV file containing test data array. If not provided, random data will be generated.",
    )
    parser.add_argument(
        "-r",
        "--repeat",
        type=int,
        default=1,
        help="If set, will repeat sending the frames a set number of times (useful for stress testing).",
    )
    return parser.parse_args()


def redis_publisher(data, shutdown_flag):
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)
    r.ping()
    print("Publisher: Connected to Redis successfully!")
    last_print_time = time.time()
    while not shutdown_flag.is_set():
        for frame in data:
            if shutdown_flag.is_set():
                break
            payload = {"timestamp": int(time.time() * 1000), "data": frame}
            r.rpush("raw_sensor_data", json.dumps(payload))

            # Print the value being sent every 5 seconds
            current_time = time.time()
            if current_time - last_print_time >= 5.0:
                print(
                    f"Publisher: Sent frame at timestamp {payload['timestamp']}. Data preview: {frame[:5]}... (Total {len(frame)} elements)"
                )
                last_print_time = current_time

            time.sleep(1 / 15.0)  # Sleep to enforce exactly 15fps


def redis_subscriber(shutdown_flag, plot_queue):
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)
    r.ping()
    print("Subscriber: Connected to Redis successfully!")
    while not shutdown_flag.is_set():
        result = r.brpop("processed_data", timeout=1)
        if result:
            # print(f"Received processed data: {result[1]}")
            try:
                data = json.loads(result[1])
                if "heart_rate" in data and "timestamp" in data:
                    plot_queue.put(
                        {
                            "timestamp": data["timestamp"],
                            "heart_rate": data["heart_rate"],
                        }
                    )
            except json.JSONDecodeError:
                pass
        time.sleep(0.01)


if __name__ == "__main__":
    args = arguement_parser()

    r = redis.Redis(host="localhost", port=6379, decode_responses=True)
    r.ping()
    print("Connected to Redis successfully!")

    # Get test Data:
    # HOLDS ALL IN MEMORY DO NOT PUT IN TOO MUCH DATA
    if args.test_data:
        print(f"Loading test data from {args.test_data}...")
        frames = []
        with open(args.test_data, "r") as f:
            for line in f:
                if line.strip():
                    frames.append([float(val) for val in line.strip().split(",")])
        print(f"Loaded {len(frames)} frames. Frame length: {len(frames[0])} floats.")
        samples = len(frames)

    # Generate static data once (as in original script)
    else:
        single_frame = [round(random.uniform(0.0, 100.0), 5) for _ in range(2048)]
        frames = [single_frame] * 1000
        samples = 1000

    shutdown_flag = multiprocessing.Event()
    plot_queue = multiprocessing.Queue()

    redis_publisher_thread = multiprocessing.Process(
        target=redis_publisher, args=(frames, shutdown_flag)
    )
    redis_publisher_thread.start()
    redis_subscriber_thread = multiprocessing.Process(
        target=redis_subscriber, args=(shutdown_flag, plot_queue)
    )
    redis_subscriber_thread.start()

    # Setup 20-second sliding window plot
    plt.ion()

    # Use a cleaner style if available, or just fallback
    try:
        plt.style.use("seaborn-v0_8-whitegrid")
    except:
        plt.style.use("ggplot")

    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor("#f8f9fa")
    ax.set_facecolor("#ffffff")

    # Modern rounded line style
    (line,) = ax.plot(
        [],
        [],
        color="#ff4b4b",
        linewidth=3.5,
        linestyle="None",
        marker="o",
        markersize=8,
        solid_capstyle="round",
    )

    timestamps = deque()
    heart_rates = deque()

    ax.set_xlabel("Time (s)", fontsize=12, fontweight="bold", color="#333333")
    ax.set_ylabel("Heart Rate (BPM)", fontsize=12, fontweight="bold", color="#333333")
    ax.set_title(
        "Live 20-Second Heart Rate Window",
        fontsize=16,
        fontweight="bold",
        pad=15,
        color="#1f2937",
    )
    ax.tick_params(colors="#555555", labelsize=10)
    ax.grid(True, linestyle="--", alpha=0.7)

    # Clean borders
    for spine in ax.spines.values():
        spine.set_color("#dddddd")
        spine.set_linewidth(1.5)

    start_time = None
    WINDOW_SIZE = 20.0

    try:
        while not shutdown_flag.is_set():
            messages_processed = False
            # Read all available data from the queue
            while not plot_queue.empty():
                try:
                    msg = plot_queue.get_nowait()
                    hr = msg.get("heart_rate")
                    ts = msg.get("timestamp") / 1000.0  # ms to seconds

                    if start_time is None:
                        start_time = ts

                    rel_ts = ts - start_time
                    timestamps.append(rel_ts)
                    heart_rates.append(hr)
                    messages_processed = True
                except Exception:
                    pass

            if messages_processed:
                # Filter out data older than WINDOW_SIZE from the latest received timestamp
                current_time = timestamps[-1]
                while (
                    len(timestamps) > 0 and (current_time - timestamps[0]) > WINDOW_SIZE
                ):
                    timestamps.popleft()
                    heart_rates.popleft()

                line.set_data(timestamps, heart_rates)

                # Expand X limits with some padding
                ax.set_xlim(
                    max(0, current_time - WINDOW_SIZE),
                    max(WINDOW_SIZE, current_time) + 0.5,
                )

                # Adjust y limits based on visible data
                if heart_rates:
                    min_hr, max_hr = min(heart_rates), max(heart_rates)
                    padding = max(5.0, (max_hr - min_hr) * 0.4)
                    ax.set_ylim(0, max_hr + padding)

                fig.canvas.draw()
                fig.canvas.flush_events()

            plt.pause(0.05)
    except KeyboardInterrupt:
        print("Interrupt received, stopping threads...")
        shutdown_flag.set()
        redis_publisher_thread.join()
        redis_subscriber_thread.join()
        print("Exited cleanly.")
