import redis, os, time, json, logging

# Setup a basic logger
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# 2. Define the background worker function
def process_data(data_points, timestamp):
    # Test calculation:
    avg = sum(data_points) / len(data_points)
    heart_rate = avg
    breathing_rate = avg / 4

    # Send the heart rate, breathing rate, and timestamp to redis to be exported.
    result = {
        "timestamp": timestamp,
        "heart_rate": heart_rate,
        "breathing_rate": breathing_rate,
    }
    r.lpush("processed_data", json.dumps(result))


# 4. The Producer (Main Thread) listening to Redis
print("Connecting to Redis...")
redis_host = os.environ.get("REDIS_HOST", "127.0.0.1")
r = redis.Redis(host=redis_host, port=6379, decode_responses=True)

print("Listening for incoming tasks...")
messages_processed = 0
time_start = time.time()
while True:
    # Blocks instantly until Redis gets a new item
    # queue_name is the Redis key, item is the actual payload
    queue_name, msg = r.blpop("raw_sensor_data", 0)

    # Depackage the data from sensor stream (if needed)
    # Should be an array of float 32s

    msg_dict = json.loads(msg)
    # Instantly hand off to the internal Python queue and go right back to listening
    # Float32 array is stored in msg)dict["data"]
    process_data(msg_dict["data"], msg_dict["timestamp"])

    messages_processed += 1
    current_time = time.time()
    if current_time - time_start >= 5.0:
        time_elapsed = current_time - time_start
        logger.info(
            f"Health Check: Processed {messages_processed} messages in the last {time_elapsed:.1f} seconds. payload processed per second (MB): {(messages_processed*len(msg)/1024/1024)/time_elapsed:.2f} MB/s"
        )
        messages_processed = 0
        time_start = current_time
