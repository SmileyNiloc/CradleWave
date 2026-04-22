import random
import time
import threading
from tqdm import tqdm  # type: ignore

# Try to use orjson for massive throughput gains on float serialization
import orjson as json  # type: ignore

from awscrt import mqtt  # type: ignore
from awsiot import mqtt_connection_builder  # type: ignore
import argparse


# Configuration
AWS_ENDPOINT = "a1py3mdrrjrz1-ats.iot.us-east-1.amazonaws.com"
CLIENT_ID = "caten_laptop"
TOPIC = "raw_sensor_data"
ROOT_CA_PATH = "root-CA.crt"
PRIVATE_KEY_PATH = "caten_laptop.private.key"
CERTIFICATE_PATH = "caten_laptop.cert.pem"

MAX_IN_FLIGHT = 50  # Keep exactly 50 messages on the wire at all times


def generate_payload_json(data):
    # Using orjson.dumps returns bytes, standard json.dumps returns str.
    # awscrt accepts either for the payload.
    ms_timestamp = time.time_ns() // 1_000_000
    package = {"timestamp": ms_timestamp, "data": data}

    if hasattr(json, "OPT_SERIALIZE_NUMPY"):  # quick check if using orjson
        return json.dumps(package)
    return json.dumps(package).encode("utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send test messages to AWS IoT")
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
    args = parser.parse_args()

    print("Configuring AWS IoT connection...")
    mqtt_connection = mqtt_connection_builder.mtls_from_path(
        endpoint=AWS_ENDPOINT,
        cert_filepath=CERTIFICATE_PATH,
        pri_key_filepath=PRIVATE_KEY_PATH,
        ca_filepath=ROOT_CA_PATH,
        client_id=CLIENT_ID,
        clean_session=False,
        keep_alive_secs=30,
    )

    print(f"Connecting to {AWS_ENDPOINT}...")
    connect_future = mqtt_connection.connect()
    connect_future.result()
    print("✅ Connected!")

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

    # Use a Semaphore to manage in-flight messages (Sliding Window)
    # This maximizes throughput while capping memory/network usage
    throttle_semaphore = threading.Semaphore(MAX_IN_FLIGHT)
    in_flight_futures = []

    def on_publish_complete(future):
        """Callback fired by the C-thread when AWS ACKs the message"""
        throttle_semaphore.release()

    print("Starting transmission...")
    start_timestamp = time.time()  # Start timing HERE, after connection

    for i in tqdm(range(samples * args.repeat), desc="Sending to AWS", unit="msg"):
        # Wait for an open slot in our sliding window
        throttle_semaphore.acquire()

        payload_bytes = generate_payload_json(frames[i % len(frames)])

        publish_future, packet_id = mqtt_connection.publish(
            topic=TOPIC,
            payload=payload_bytes,
            qos=mqtt.QoS.AT_LEAST_ONCE,
        )

        # Attach non-blocking callback to release the semaphore slot
        publish_future.add_done_callback(on_publish_complete)
        in_flight_futures.append(publish_future)

    # Wait for the very last batch to finish acknowledging
    for future in in_flight_futures:
        future.result()

    total_time = time.time() - start_timestamp
    print("✅ All messages published and acknowledged!")

    print("Disconnecting...")
    mqtt_connection.disconnect().result()

    # Metrics
    sample_payload_len = len(generate_payload_json(frames[0]))
    print(f"Total time taken: {total_time:.2f} seconds")
    print(
        f"Sent {samples * args.repeat} frames in {total_time:.2f} seconds ({(samples * args.repeat)/total_time:.2f} frames/sec)"
    )
    print(f"Average time per frame: {total_time/(samples * args.repeat):.4f} seconds")
    print(f"Average payload size: {sample_payload_len} bytes")
    print(
        f"Average MB per second: {(sample_payload_len*samples)/total_time/1024/1024:.2f} MB/sec"
    )
