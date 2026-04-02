from fastapi import FastAPI  # type: ignore
from contextlib import asynccontextmanager
from awscrt import mqtt, auth  # type: ignore
from fastapi.middleware.cors import (  # pyright: ignore[reportMissingImports]
    CORSMiddleware,
)  # Import the middleware
import json, redis, os

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
        processor_data = redis_conn.lpop("processed_data")
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
def redis_info():
    global redis_conn
    if redis_conn is None:
        return {"error": "Redis connection not established."}
    try:
        info = redis_conn.info()
        return {"redis_info": info}
    except Exception as e:
        return {"error": f"Failed to get Redis info: {str(e)}"}
