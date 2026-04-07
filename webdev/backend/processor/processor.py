import redis, os, time, json


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
    print(f"Processed data: {result}")


# 4. The Producer (Main Thread) listening to Redis
print("Connecting to Redis...")
redis_host = os.environ.get("REDIS_HOST", "127.0.0.1")
r = redis.Redis(host=redis_host, port=6379, decode_responses=True)

print("Listening for incoming tasks...")
while True:
    # Blocks instantly until Redis gets a new item
    # queue_name is the Redis key, item is the actual payload
    queue_name, msg = r.blpop("raw_sensor_data", 0)

    # Depackage the data from sensor stream (if needed)
    # Should be an array of float 32s
    print(f"Received msg: {msg}")

    msg_dict = json.loads(msg)
    # Instantly hand off to the internal Python queue and go right back to listening
    # Float32 array is stored in msg)dict["data"]
    process_data(msg_dict["data"], msg_dict["timestamp"])
