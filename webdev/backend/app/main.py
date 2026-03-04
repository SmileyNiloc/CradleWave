from fastapi import FastAPI, Request, WebSocket  # pyright: ignore[reportMissingImports]
from fastapi.middleware.cors import (
    CORSMiddleware,
)  # pyright: ignore[reportMissingImports] # Import the middleware
from dotenv import load_dotenv  # pyright: ignore[reportMissingImports]
import os
import json
import msgpack
import time, datetime

from google.cloud import firestore  # pyright: ignore[reportMissingImports]
from cachetools import TTLCache  # For caching metadata

from awsiot import mqtt_connection_builder
import time

app = FastAPI()

# List of origins that are allowed to make requests
origins = [
    # "http://localhost:5047",
    "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/hello")
def hello():
    return {"message": "Hello, World!"}


@app.get("/")
def root():
    return {"message": "Welcome to the CradleWave API"}


# CHANGE SO THAT WORKFLOW GENERATES THE REQUIRENMENTS>TXT FILE


# No .pem files needed!
connection = mqtt_connection_builder.websockets_with_default_aws_signing(
    endpoint="a1py3mdrrjrz1-ats.iot.us-east-2.amazonaws.com",
    region="us-east-2",
    client_id="EC2_Backend_Client",
)

print("Connecting...")
connection.connect().result()
print("Connected!")

connection.publish(topic="sdk/test/ec2", payload='{"msg": "Success from EC2!"}', qos=1)
print("Published!")

connection.disconnect().result()
