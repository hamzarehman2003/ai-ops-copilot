from fastapi import FastAPI

from app.routers import health, sources

app = FastAPI(title="AI Operations Copilot", version="0.1.0")

app.include_router(health.router)
app.include_router(sources.router)
