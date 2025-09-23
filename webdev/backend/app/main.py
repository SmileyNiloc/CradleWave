from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware # Import the middleware


app = FastAPI()

#List of origins that are allowed to make requests
origins = [
    "http://localhost:5047",
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