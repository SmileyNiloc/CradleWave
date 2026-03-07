from fastapi import FastAPI  # type: ignore
from contextlib import asynccontextmanager
from awsiot import mqtt_connection_builder  # type: ignore
from awscrt import mqtt, auth  # type: ignore
from fastapi.middleware.cors import (  # pyright: ignore[reportMissingImports]
    CORSMiddleware,
)  # Import the middleware
import json, redis

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
    global last_message
    print(f"Received message on topic {topic}: {payload}")
    last_message = json.loads(payload)


@asynccontextmanager
async def lifespan(app: FastAPI):
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


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/publish-test")
async def test_publish():
    # Now you can use the global connection inside your routes
    mqtt_conn.publish(
        topic="sdk/test/ec2",
        payload='{"status": "API is live"}',
        qos=mqtt.QoS.AT_LEAST_ONCE,
    )
    return {"status": "Message sent from route!"}


@app.get("/api/last-message")
async def get_last_message():
    global last_message
    if last_message is not None:
        return {"last_message": last_message}
    else:
        return {"last_message": "No messages received yet."}


@app.get("/")
def root():
    return {"message": "Welcome to the CradleWave API"}


@app.get("/api/redis-info")
def redis_info():
    global redis_conn
    if redis_conn is None:
        return {"error": "Redis connection not established."}
    try:
        info = redis_conn.info()
        return {"redis_info": info}
    except Exception as e:
        return {"error": f"Failed to get Redis info: {str(e)}"}


# CHANGE SO THAT WORKFLOW GENERATES THE REQUIRENMENTS>TXT FILE
