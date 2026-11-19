from fastapi import FastAPI

app = FastAPI(
    title="Lawyer AI API",
    description="An API for Lawyer AI, providing legal assistance and information."
)



@app.get("/")
def root():
    return {
        "message": "App is running!"
    }