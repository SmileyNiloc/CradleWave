from concurrent import futures
import random, time, json
from awscrt import mqtt  # type: ignore
from awsiot import mqtt_connection_builder  # type: ignore
from tqdm import tqdm  # type: ignore

# Configure AWS IoT connection
AWS_ENDPOINT = "a1py3mdrrjrz1-ats.iot.us-east-1.amazonaws.com"
CLIENT_ID = "caten_laptop"
TOPIC = "raw_sensor_data"

ROOT_CA_PATH = "root-CA.crt"
PRIVATE_KEY_PATH = "caten_laptop.private.key"
CERTIFICATE_PATH = "caten_laptop.cert.pem"


# Create a payload with a timestamp and an array of 2048 random float32 values
def generate_payload():
    ms_timestamp = time.time_ns() // 1_000_000
    float_array = [round(random.uniform(0.0, 100.0), 5) for _ in range(2048)]
    return {"timestamp": ms_timestamp, "data": float_array}


# Create a payload with a timestamp data in json dumps format
def generate_payload_json(data):
    ms_timestamp = time.time_ns() // 1_000_000
    package = {"timestamp": ms_timestamp, "data": data}
    return json.dumps(package)


if __name__ == "__main__":
    start_timestamp = time.time()

    # 1. Build the MQTT Connection using the AWS mTLS builder
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

    # 2. Connect
    print(f"Connecting to {AWS_ENDPOINT}...")
    # The SDK uses "futures" (promises) for asynchronous operations
    connect_future = mqtt_connection.connect()

    # .result() pauses the script until the connection is fully established
    connect_future.result()
    print("✅ Connected!")

    # Array to hold future acks from aws
    futures = []

    # Fake Payload Generation
    data = [round(random.uniform(0.0, 100.0), 5) for _ in range(2048)]

    samples = 1000
    # 3. Publish Data to MQTT Topic
    for i in tqdm(range(samples), desc="Sending to AWS", unit="msg"):
        json_payload = generate_payload_json(data)
        publish_future, packet_id = mqtt_connection.publish(
            topic=TOPIC,
            payload=json_payload,
            qos=mqtt.QoS.AT_MOST_ONCE,  # Equivalent to QoS 0
        )
        # QoS 0 means "fire and forget" - the client won't wait for an acknowledgment from the server. This is faster but less reliable.

        # print(
        #     f"Publishing message {i+1}: {json_payload[:100]}... to topic '{TOPIC}'..."
        # )
    total_time = time.time() - start_timestamp

    # Now wait for AWS to acknowledge all of the futures
    # print("Waiting for AWS acknowledgements...")
    # for future in tqdm(futures, desc="Acknowledging", unit="ack"):
    #     future.result()  # Wait for the PUBACKs
    print("All messages successfully sent")

    # 4. Disconnect cleanly
    print("Disconnecting...")
    disconnect_future = mqtt_connection.disconnect()
    disconnect_future.result()
    print("Disconnected.")
    print(f"Total time taken: {total_time:.2f} seconds")
    print(
        f"Sent {samples} frames in {total_time:.2f} seconds ({samples/total_time:.2f} frames/sec)"
    )
    print(f"Average time per frame: {total_time/samples:.4f} seconds")
    print(f"Average payload size: {len(json_payload)} bytes")
    print(
        f"Average MB per second: {(len(json_payload)*samples)/total_time/1024/1024:.2f} MB/sec"
    )
