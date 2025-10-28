from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware # Import the middleware

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

@app.get("/api/hello")
def hello():
    return {"message": "Hello, World!"}

@app.get("/")
def root():
    return {"message": "Welcome to the CradleWave API"}

@app.get("/api/test2")
def test_endpoint2():
    return {"message": "This is a test GET endpoint!"}

@app.get("/api/test")
async def test_endpoint(request: Request):
    req = await request.json()
    response = {"message": "This is a test POST endpoint (but using GET)!",
                "request": req}
    return response
@app.post("/")
async def root_post(request: Request):
    req = await request.json()
    return req