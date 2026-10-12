import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.rate_limit import limiter
from app.routers import admin, dev, gestor, helipagos, macroclick, mp, public

app = FastAPI(title="Coopera API")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Local-disk uploads are only the fallback for when R2 isn't configured. On a
# read-only filesystem (serverless) the directory can't be created, so there
# is nothing to serve.
try:
    os.makedirs(settings.upload_dir, exist_ok=True)
except OSError:
    pass
else:
    app.mount("/static", StaticFiles(directory=settings.upload_dir), name="static")

app.include_router(public.router)
app.include_router(admin.router)
app.include_router(gestor.router)
app.include_router(dev.router)
app.include_router(mp.router)
app.include_router(helipagos.router)
app.include_router(macroclick.router)


@app.get("/health")
def health():
    return {"status": "ok"}
