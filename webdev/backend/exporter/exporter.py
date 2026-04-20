import logging, os, firebase_admin, threading, redis, queue, time, json
from firebase_admin import credentials, firestore
from datetime import datetime


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Setup Google Firestore Connection
SERVICE_ACCOUNT_KEY = os.environ.get(
    "GOOGLE_KEY", "/app/certs/cradlewave-aa74f-firebase-adminsdk.json"
)

cred = credentials.Certificate(SERVICE_ACCOUNT_KEY)
firebase_admin.initialize_app(cred)
db = firestore.client()

# Global Threading event to signal shutdown
shutdown_flag = threading.Event()


def send_vitals_to_firestore_batch(device: str, collection: str, vitals_list: list):
    """
    vitals_list should be a list of dicts:
    [{'timestamp': dt, 'heart_rate': 70, 'breathing_rate': 16}, ...]
    """
    batch = db.batch()

    # 1. Group data by document_id (the hour) to avoid multiple updates to one doc
    grouped_data = {}

    for v in vitals_list:
        doc_id = v["timestamp"].strftime("%Y-%m-%d-%H")
        if doc_id not in grouped_data:
            grouped_data[doc_id] = []

        # Prepare the data point exactly as before
        grouped_data[doc_id].append(
            {
                "timestamp": v["timestamp"],
                "heart_rate": v["heart_rate"],
                "breathing_rate": v["breathing_rate"],
            }
        )

    # 2. Add each unique document update to the batch
    for doc_id, points in grouped_data.items():
        doc_ref = (
            db.collection("devices")
            .document(device)
            .collection(collection)
            .document(doc_id)
        )

        # Use ArrayUnion with the entire list of points for that hour
        batch.set(doc_ref, {"data_points": firestore.ArrayUnion(points)}, merge=True)

    # 3. Commit the batch
    batch.commit()


import json
import time
from datetime import datetime


def redis_firestore_batch_worker(
    redis_conn, device, collection, redis_name, batch_size=100, wait_time=2.0
):
    """
    Continuously listens to the Redis list. When an item arrives, it waits
    a couple of seconds to allow the queue to build up, then flushes out of
    Redis in bulk.
    """
    while not shutdown_flag.is_set():
        try:
            # 1. Block until at least one item is available
            result = redis_conn.brpop(redis_name, timeout=2)
            if not result:
                continue  # Timeout occurred, loop back and check shutdown_flag
            _, data = result

            # Start a list of RAW strings
            raw_items = [data]

            # 2. Wait up to `wait_time` seconds to let the queue fill up
            # We sleep in 0.1s increments so we can still respond to shutdowns instantly
            start_wait = time.time()
            while (time.time() - start_wait) < wait_time and not shutdown_flag.is_set():
                # Optimization: Stop waiting early if we already have enough items for a full batch
                if redis_conn.llen(redis_name) >= (batch_size - 1):
                    break
                time.sleep(0.1)

            # If shut down during the wait, we still process the single item we popped
            # to ensure we don't lose it.

            # 3. Pipeline the rest of the batch
            if batch_size > 1:
                pipe = redis_conn.pipeline()
                for _ in range(batch_size - 1):
                    pipe.rpop(redis_name)

                # Execute all RPOPs in one network round trip
                additional_items = pipe.execute()
                valid_additional_items = [
                    item for item in additional_items if item is not None
                ]
                raw_items.extend(valid_additional_items)

            # 4. Process the entire batch in one loop
            batch = []
            for item in raw_items:
                if item is not None:
                    try:
                        item_json = json.loads(item)
                        # Convert epoch ms to datetime for EVERY item
                        item_json["timestamp"] = datetime.fromtimestamp(
                            item_json.get("timestamp", 0) / 1000
                        )
                        batch.append(item_json)
                    except Exception as parse_e:
                        logger.error(f"Error parsing JSON/Date: {parse_e}")

            # 5. Send to Firestore
            if batch:
                try:
                    send_vitals_to_firestore_batch(device, collection, batch)
                    logger.info(
                        f"Flushed batch of {len(batch)} data points to Firestore"
                    )
                except Exception as e:
                    logger.error(f"Error sending batch to Firestore: {e}")
                    # Push everything back into Redis if Firestore fails so no data is lost
                    if raw_items:
                        redis_conn.lpush(redis_name, *raw_items)

        except Exception as e:
            logger.error(f"Error in batch consumer: {e}")
            time.sleep(1)  # Back off on error


if __name__ == "__main__":
    redis_host = os.environ.get("REDIS_HOST", "127.0.0.1")
    redis_port = 6379

    print(f"Connecting to Redis on {redis_host}:{redis_port}...")
    while True:
        try:
            redis_conn = redis.Redis(
                host=redis_host, port=redis_port, decode_responses=True
            )
            redis_conn.ping()
            print("Successfully connected to Redis.")
            break
        except redis.ConnectionError as e:
            logger.warning(f"Waiting for Redis to start... {e}")
            time.sleep(2)

    redis_firestore_worker = threading.Thread(
        target=redis_firestore_batch_worker,
        args=(redis_conn, "demo_pcb", "filtered_data", "processed_data", 250, 5.0),
        daemon=True,
    )
    redis_firestore_worker.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down workers...")
        shutdown_flag.set()
        redis_firestore_worker.join()  # Waits for the thread to exit cleanly
        logger.info("Worker shutdown complete.")
    except redis.ConnectionError as e:
        logger.warning(f"Redis connection error: {e}")
        time.sleep(2)
        while True:
            try:
                redis_conn = redis.Redis(
                    host=redis_host, port=redis_port, decode_responses=True
                )
                redis_conn.ping()
                print("Successfully connected to Redis.")
                break
            except redis.ConnectionError as e:
                logger.warning(f"Retrying Redis connection: {e}")
                time.sleep(2)
