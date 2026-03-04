from fastapi import FastAPI
from contextlib import asynccontextmanager
from awsiot import mqtt_connection_builder
from awscrt import mqtt, auth
from fastapi.middleware.cors import (
    CORSMiddleware,
)  # pyright: ignore[reportMissingImports] # Import the middleware
import json

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


@app.get("/api/hello")
def hello():
    return {"message": "Hello, World!"}


@app.get("/")
def root():
    return {"message": "Welcome to the CradleWave API"}


# CHANGE SO THAT WORKFLOW GENERATES THE REQUIRENMENTS>TXT FILE
