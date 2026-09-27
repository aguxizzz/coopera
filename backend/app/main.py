import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, engine, run_simple_migrations
from app.routers import admin, dev, public

Base.metadata.create_all(bind=engine)
run_simple_migrations()

os.makedirs(settings.upload_dir, exist_ok=True)

app = FastAPI(title="Coopera API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=settings.upload_dir), name="static")

app.include_router(public.router)
app.include_router(admin.router)
app.include_router(dev.router)


@app.get("/health")
def health():
    return {"status": "ok"}
