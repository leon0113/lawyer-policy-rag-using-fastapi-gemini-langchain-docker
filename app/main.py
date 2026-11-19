from fastapi import FastAPI
from database import init_db
from contextlib import asynccontextmanager
from routes.contracts import router as contracts_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="Lawyer AI API",
    description="An API for Lawyer AI, providing legal assistance and information.",
    lifespan=lifespan
)

app.include_router(contracts_router)

@app.get("/")
def root():
    return {
        "message": "App is running!"
    }