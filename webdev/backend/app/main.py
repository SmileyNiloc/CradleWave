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

load_dotenv()  # Load environment variables from .env file

ENV = os.getenv("ENVIRONMENT", "production")
print(ENV)

if ENV == "developement":
    project_id = os.getenv("FIRESORE_PROJECT_ID")
    db = firestore.Client(project=project_id)
else:
    db = firestore.Client()
clients = set()


@app.post("/test/add")
async def add_data(data: dict):
    doc_ref = db.collection("test_collection").document()
    print(data)
    doc_ref.set(data)
    return {"message": "Data added successfully", "id": doc_ref.id}


@app.websocket("/test/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    print("Client connected")

    try:
        while True:
            # Receive message from client
            data = {}
            data["text"] = await websocket.receive_text()
            print(f"Received: {data['text']}")
            try:
                data["json"] = json.loads(data["text"])

                if data["json"].get("collection", None):
                    collection_name = data["json"]["collection"]
                    doc_name = data["json"].get("document", None)
                    doc_ref = (
                        db.collection(collection_name).document(doc_name)
                        if doc_name
                        else db.collection(collection_name).document()
                    )
                    doc_ref.set(data["json"].get("data", {}))
                    print(
                        f"Data added to collection {collection_name} with ID {doc_ref.id}"
                    )
            except Exception as e:
                print(f"Error processing data: {e}")
                continue

    except Exception as e:
        print(f"Client disconnected: {e}")
        clients.remove(websocket)


@app.get("/api/hello")
def hello():
    return {"message": "Hello, World!"}


@app.get("/")
def root():
    return {"message": "Welcome to the CradleWave API"}


@app.post("/api/test")
async def test_endpoint(request: Request):
    req = await request.json()
    response = {
        "message": "This is a test POST endpoint (but using GET)!",
        "request": req,
    }
    return response


@app.websocket("/ws/")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    print("Client connected")

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            print(f"Received: {data}")

            # Broadcast message to all connected clients
            for client in clients:
                if client != websocket:
                    await client.send_text(f"Echo: {data}")
    except Exception as e:
        print(f"Client disconnected: {e}")
        clients.remove(websocket)


@app.websocket("/ws/filtered")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    print("Client connected")

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_bytes()
            print(f"Received: {data}")

            # unpack the binary data
            unpacked_data = msgpack.unpackb(data)
            print(f"Unpacked Data: {unpacked_data}")

            # Connect to filtered_data collection
            collection_name = "filtered_data"
            doc_ref = db.collection(collection_name).document()
            doc_ref.set(unpacked_data)
            print(f"Data added to collection {collection_name} with ID {doc_ref.id}")

    except Exception as e:
        print(f"Client disconnected: {e}")
        clients.remove(websocket)


@app.websocket("/ws/heart_rate")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    print("Client connected")

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_bytes()
            print(f"Received: {data}")

            # unpack the binary data
            unpacked_data = msgpack.unpackb(data)
            print(f"Unpacked Data: {unpacked_data}")

            device_id = unpacked_data.get("device", "unknown_user")
            session_id = unpacked_data.get("session_id", "unknown_session")
            timestamp = unpacked_data.get("timestamp", time.time())
            data = unpacked_data.get("data", {})

            # Build Firestore path:
            # devices/{device_id}/sessions/{session_id}/heart_rate
            session_ref = (
                db.collection("devices")
                .document(device_id)
                .collection("sessions")
                .document(session_id)
            )
            # Ensure session document exists
            if not session_ref.get().exists:
                session_ref.set(
                    {
                        "session_id": session_id,
                        "user_id": device_id,
                    },
                    merge=True,
                )
                print(f"Created session doc for {device_id}/{session_id}")

            session_ref.collection("heart_rate_data").add(
                {"time": data.get("time"), "heart_rate": data.get("heart_rate")}
            )

            # # Append to array field
            # session_ref.update({
            #     "heart_rate_data": firestore.ArrayUnion([
            #         {"time": data.get("time"),
            #          "heart_rate": data.get("heart_rate")}])
            # })

            print(f"Added HR data for {device_id}/{session_id} at {timestamp}")
    except Exception as e:
        print(f"Client disconnected: {e}")
        clients.remove(websocket)


session_cache = {}


@app.websocket("/ws/data_handler")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    print("Client connected")

    try:
        while True:
            # Receive binary
            raw = await websocket.receive_bytes()
            unpacked_data = msgpack.unpackb(raw)

            device_id = unpacked_data.get("device", "unknown_user")
            session_id = unpacked_data.get("session_id", "unknown_session")
            timestamp = unpacked_data.get("timestamp", time.time())
            data = unpacked_data.get("data", {})

            session_ref = (
                db.collection("devices")
                .document(device_id)
                .collection("sessions")
                .document(session_id)
            )

            # Ensure session exists
            snapshot = await run_in_threadpool(session_ref.get)
            if not snapshot.exists:
                await run_in_threadpool(
                    session_ref.set,
                    {"session_id": session_id, "user_id": device_id},
                    merge=True,
                )

            # Read cached metadata
            meta = session_cache.get((device_id, session_id), {})
            frame_rate = meta.get("frame_rate", 15)

            # Process incoming keys
            for key, value in data.items():

                # --- METADATA ---
                if key == "metadata":
                    session_cache[(device_id, session_id)] = value
                    await run_in_threadpool(session_ref.set, {key: value}, True)
                    continue

                # --- FRAME / HR DATA ---
                if key in ("frame_data", "heart_rate_data"):
                    frame_count = value.get("frame_count")
                    if frame_count is None:
                        print("Missing frame_count")
                        continue

                    entry = dict(value)
                    entry["relative_time"] = frame_count / frame_rate

                    sub = session_ref.collection(key)
                    await run_in_threadpool(sub.add, entry)
                    continue

                # --- OTHER FIELDS ---
                sub = session_ref.collection(key)
                await run_in_threadpool(sub.add, value)

    except Exception as e:
        print(f"Client disconnected: {e}")
        clients.discard(websocket)
