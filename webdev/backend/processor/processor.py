import redis, os, time, json


# 2. Define the background worker function
def process_data(data_points):
    # Test calculation:
    avg = sum(data_points) / len(data_points)
    result = {"time": time.time(), "average": avg}
    r.lpush("processed_data", json.dumps(result))


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
    data_points = msg_dict["data"]

    # Instantly hand off to the internal Python queue and go right back to listening
    process_data(data_points)
