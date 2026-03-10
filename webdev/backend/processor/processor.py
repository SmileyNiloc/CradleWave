import redis
import time
import json


# 2. Define the background worker function
def process_data(data_points):
    # Test calculation:
    avg = sum(data_points) / len(data_points)
    r.lpush("processed_data", {"time": time.time(), "average": avg})


# 4. The Producer (Main Thread) listening to Redis
print("Connecting to Redis...")
r = redis.Redis(host="redis", port=6379, decode_responses=True)

print("Listening for incoming tasks...")
while True:
    # Blocks instantly until Redis gets a new item
    # queue_name is the Redis key, item is the actual payload
    queue_name, msg = r.blpop("raw_sensor_data", 0)

    # Depackage the data from sensor stream (if needed)
    # Should be an array of float 32s
    print(f"Received msg: {msg}")

    # Instantly hand off to the internal Python queue and go right back to listening
    process_data(msg["data"])
