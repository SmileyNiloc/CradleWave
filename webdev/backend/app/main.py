from fastapi import FastAPI, Request, WebSocket # pyright: ignore[reportMissingImports]
from fastapi.middleware.cors import CORSMiddleware # pyright: ignore[reportMissingImports] # Import the middleware
from dotenv import load_dotenv # pyright: ignore[reportMissingImports]
import os
import json

from google.cloud import firestore  # pyright: ignore[reportMissingImports]

app = FastAPI()

#List of origins that are allowed to make requests
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

ENV = os.getenv("ENVIRONMENT","production")
print(ENV)

if ENV == "developement":
    project_id = os.getenv("FIRESORE_PROJECT_ID")
    db = firestore.Client(project=project_id)
else:
    db = firestore.Client()
clients = set()

@app.post("/test/add")
async def add_data(data: dict):
    doc_ref = db.collection('test_collection').document()
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
            data['text'] = await websocket.receive_text()
            print(f"Received: {data['text']}")
            try:
                data['json'] = json.loads(data['text'])

                if(data['json'].get('collection',None)):
                    collection_name = data['json']['collection']
                    doc_name = data['json'].get('document',None)
                    doc_ref = db.collection(collection_name).document(doc_name) if doc_name else db.collection(collection_name).document()
                    doc_ref.set(data['json'].get('data',{}))
                    print(f"Data added to collection {collection_name} with ID {doc_ref.id}")
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
    response = {"message": "This is a test POST endpoint (but using GET)!",
                "request": req}
    return response

@app.websocket("/ws")
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