from fastapi import FastAPI

app = FastAPI()

@app.get("/api/hello")
def hello():
    return {"message": "Hello, World!"}

@app.get("/")
def root():
    return {"message": "Welcome to the CradleWave API"}