import time
import json
from awscrt import mqtt
from awsiot import mqtt_connection_builder

# Configuration
AWS_ENDPOINT = "a1py3mdrrjrz1-ats.iot.us-east-1.amazonaws.com"
CLIENT_ID = "caten_laptop"
TOPIC = "raw_sensor_data"
ROOT_CA_PATH = "root-CA.crt"
PRIVATE_KEY_PATH = "caten_laptop.private.key"
CERTIFICATE_PATH = "caten_laptop.cert.pem"

count = 0


def on_message_received(topic, payload, dup, qos, retain, **kwargs):
    global count
    count += 1

    try:
        payload_str = payload
        print(payload_str)

        # timestamp_ms = data.get("timestamp", 0)
        # sensor_data = data.get("data", [])

        # current_time_ms = int(time.time() * 1000)
        # latency = current_time_ms - timestamp_ms if timestamp_ms else None

        # print(f"[{count}] --- Message Received ---")
        # print(f"Topic:       {topic}")
        # print(f"Payload:     {len(payload)} bytes")
        # print(f"Data Points: {len(sensor_data)}")
        # if latency is not None:
        #     print(f"Latency:     {latency} ms")

        # if len(sensor_data) >= 2:
        #     print(f"Preview:     [{sensor_data[0]}, ..., {sensor_data[-1]}]")
        # print("-" * 30 + "\n")

    except Exception as e:
        print(
            f"[{count}] Received raw payload ({len(payload)} bytes). Could not parse JSON: {e}"
        )


if __name__ == "__main__":
    print("Configuring AWS IoT connection...")
    mqtt_connection = mqtt_connection_builder.mtls_from_path(
        endpoint=AWS_ENDPOINT,
        cert_filepath=CERTIFICATE_PATH,
        pri_key_filepath=PRIVATE_KEY_PATH,
        ca_filepath=ROOT_CA_PATH,
        client_id=CLIENT_ID,
        clean_session=True,  # Fresh session for subscriber
        keep_alive_secs=30,
    )

    print("Connecting...")
    mqtt_connection.connect().result()
    print("✅ Connected!")

    print(f"Subscribing to '{TOPIC}'...")
    subscribe_future, _ = mqtt_connection.subscribe(
        topic=TOPIC, qos=mqtt.QoS.AT_LEAST_ONCE, callback=on_message_received
    )
    subscribe_future.result()
    print("✅ Subscribed! Waiting for messages... (Ctrl+C to exit)\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nDisconnecting...")
        mqtt_connection.disconnect().result()
        print("✅ Disconnected!")
