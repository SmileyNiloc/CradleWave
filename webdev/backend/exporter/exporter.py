from fastapi import FastAPI  # type: ignore
from contextlib import asynccontextmanager
from awscrt import mqtt, auth  # type: ignore
from fastapi.middleware.cors import (  # pyright: ignore[reportMissingImports]
    CORSMiddleware,
)  # Import the middleware
import json, os, asyncio
import redis.asyncio as redis
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timezone

SERVICE_ACCOUNT_KEY = os.environ.get(
    "GOOGLE_KEY", "/app/certs/cradlewave-aa74f-firebase-adminsdk.json"
)


cred = credentials.Certificate(SERVICE_ACCOUNT_KEY)

firebase_admin.initialize_app(cred)
db = firestore.client()

# List of origins that are allowed to make requests
origins = [
    # "http://localhost:5047",
    "*"
]

# Global variables
# Hold last value (testing)
last_message = None
# Hold Redis connection
redis_conn = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # connect to Redis
    global redis_conn
    redis_host = os.environ.get("REDIS_HOST", "127.0.0.1")
    redis_conn = redis.Redis(host=redis_host, port=6379, decode_responses=True)

    asyncio.create_task(
        listen_to_queue("processed_data")
    )  # Start listening to the Redis queue in the background

    yield  # The app runs here


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/redis-data-test")
async def redis_test():
    global redis_conn
    if redis_conn is None:
        return {"error": "Redis connection not established."}
    try:
        processor_data = await redis_conn.lpop("processed_data")
        return {"redis_test": processor_data}
    except Exception as e:
        return {"error": f"Failed to test Redis connection: {str(e)}"}


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
async def redis_info():
    global redis_conn
    if redis_conn is None:
        return {"error": "Redis connection not established."}
    try:
        info = await redis_conn.info()
        return {"redis_info": info}
    except Exception as e:
        return {"error": f"Failed to get Redis info: {str(e)}"}


def send_vitals_to_firestore(
    device: str,
    collection: str,
    timestamp: datetime,
    heart_rate: int,
    breathing_rate: int,
):
    data_point = {
        "timestamp": timestamp,
        "heart_rate": heart_rate,
        "breathing_rate": breathing_rate,
    }
    document_id = timestamp.strftime("%Y-%m-%d-%H")
    doc_ref = (
        db.collection("devices")
        .document(device)
        .collection(collection)
        .document(document_id)
    )
    doc_ref.set({"data_points": firestore.ArrayUnion([data_point])}, merge=True)
    print(f"Sent data point to Firestore: {data_point}")


async def listen_to_queue(queue_name: str):
    global redis_conn
    if redis_conn is None:
        print("Redis connection not established.")
        return
    while True:
        try:
            message = await redis_conn.blpop(queue_name, timeout=0)
            if message:
                _, data = message
                print(f"Received message from Redis: {data}")
                # Process the data and send to Firestore
                # For example, if data is a JSON string with heart_rate and breathing_rate:
                try:
                    data_dict = json.loads(data)
                    timestamp = datetime.fromtimestamp(
                        data_dict.get("timestamp", 0) / 1000
                    )  # Assuming timestamp is in milliseconds
                    # Firestore is synchronous, we run in background thread
                    await asyncio.to_thread(
                        send_vitals_to_firestore,
                        device="demo_pcb",
                        collection="filtered_data",
                        timestamp=timestamp,
                        heart_rate=data_dict.get("heart_rate", 0),
                        breathing_rate=data_dict.get("breathing_rate", 0),
                    )
                except json.JSONDecodeError as e:
                    print(f"Failed to decode JSON: {str(e)}")
        except Exception as e:
            print(f"Error while listening to Redis queue: {str(e)}")
            await asyncio.sleep(1) # Prevent tight loop on error


@app.get("/api/send-firestore-test")
def send_firestore_test():
    # Will have to change the timestamp stuff!
    try:
        send_vitals_to_firestore(
            "demo_pcb", "filtered_data", datetime.now(timezone.utc), 72, 16
        )
    except Exception as e:
        return {"error": f"Failed to send test data to Firestore: {str(e)}\n"}
    return {"message": "Test data sent to Firestore\n"}
