from contextlib import asynccontextmanager
from awsiot import mqtt_connection_builder  # type: ignore
from awscrt import mqtt, auth  # type: ignore
import json, redis
import asyncio

# List of origins that are allowed to make requests
origins = [
    # "http://localhost:5047",
    "*"
]

# Global variables
# hold persistent connection
mqtt_conn = None
# Hold last value (testing)
last_message = None
# Hold Redis connection
redis_conn = None

# This is what talks to the IAM Role on your EC2
credentials_provider = auth.AwsCredentialsProvider.new_default_chain()


# Callback function for when a message is received (for testing)
def on_message_received(topic, payload, **kwargs):
    # global last_message
    # print(f"Received message on topic {topic}: {payload}")
    sensor_data = payload.decode("utf-8")  # Decode bytes to string
    # Redis only stores bytes or strings, MAYBE CHANGE TO JUST INPUT raw BYTES AND THEN LOAD IN PROCESSOR
    # Store the message in Redis as a stringified JSON
    if redis_conn:
        redis_conn.lpush("raw_sensor_data", sensor_data)


@asynccontextmanager
async def lifespan():
    # --- Startup: Connect to IoT Core ---
    global mqtt_conn
    mqtt_conn = mqtt_connection_builder.websockets_with_default_aws_signing(
        endpoint="a1py3mdrrjrz1-ats.iot.us-east-2.amazonaws.com",
        region="us-east-2",
        client_id="EC2_Backend_Client",
        credentials_provider=credentials_provider,
    )

    print("Connecting to IoT Core...")
    mqtt_conn.connect().result()
    print("Connected!")

    subscribe_topic = "sdk/test/"

    subscribe_future, packet_id = mqtt_conn.subscribe(
        topic=subscribe_topic,
        qos=mqtt.QoS.AT_LEAST_ONCE,
        callback=on_message_received,
    )
    subscribe_result = subscribe_future.result()
    print(f"Subscribed to {subscribe_topic} with {subscribe_result['qos']} QoS")

    # connect to Redis
    global redis_conn
    redis_conn = redis.Redis(host="redis", port=6379, decode_responses=True)

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
