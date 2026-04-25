from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from app.routers import picks
from app.models.strikeout import strikeout_model

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-load model artifact at startup so first request isn't slow
    try:
        strikeout_model.load()
        print("[OK] Strikeout model loaded")
    except FileNotFoundError:
        print("[WARN] Model artifact not found -- run train/train_strikeout.py first")
    yield


app = FastAPI(
    title="mlbet API",
    description="ML-powered baseball prop edge finder",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(picks.router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_loaded": strikeout_model.is_loaded,
    }
