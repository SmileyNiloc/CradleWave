from fastapi import FastAPI  # type: ignore
from contextlib import asynccontextmanager
from awscrt import mqtt, auth  # type: ignore
from fastapi.middleware.cors import (  # pyright: ignore[reportMissingImports]
    CORSMiddleware,
)  # Import the middleware
import json, os, asyncio, logging, time
import redis.asyncio as redis
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timezone

# Setup a basic logger
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

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
        logger.error("Redis connection not established. Exiting queue listener.")
        return

    # Trackers for throttled logging
    messages_processed = 0
    last_log_time = time.time()

    logger.info(f"Started listening to Redis queue: '{queue_name}'...")

    while True:
        try:
            # blpop blocks until a message is available
            message = await redis_conn.blpop(queue_name, timeout=0)
            if message:
                _, data = message

                try:
                    data_dict = json.loads(data)
                    timestamp = datetime.fromtimestamp(
                        data_dict.get("timestamp", 0) / 1000
                    )

                    # Firestore is synchronous, we run in background thread
                    await asyncio.to_thread(
                        send_vitals_to_firestore,
                        device="demo_pcb",
                        collection="filtered_data",
                        timestamp=timestamp,
                        heart_rate=data_dict.get("heart_rate", 0),
                        breathing_rate=data_dict.get("breathing_rate", 0),
                    )

                    # --- Throttled Logging Logic ---
                    messages_processed += 1
                    current_time = time.time()
                    time_elapsed = current_time - last_log_time

                    # Log a health check every 5 seconds
                    if time_elapsed >= 5.0:
                        msg_per_sec = messages_processed / time_elapsed
                        logger.info(
                            f"Queue Health: Pushed {messages_processed} msgs to Firestore "
                            f"in {time_elapsed:.1f}s ({msg_per_sec:.1f} msg/s)."
                        )

                        # Reset trackers
                        messages_processed = 0
                        last_log_time = current_time

                except json.JSONDecodeError as e:
                    # Log the specific error AND the malformed data so you can debug it
                    logger.error(f"Failed to decode JSON: {str(e)} | Raw data: {data}")

        except Exception as e:
            # exc_info=True forces the logger to print the full traceback to Docker
            logger.error(
                f"Critical error while listening to Redis queue: {str(e)}",
                exc_info=True,
            )
            await asyncio.sleep(1)  # Prevent tight loop on error


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
