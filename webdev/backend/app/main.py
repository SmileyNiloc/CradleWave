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
