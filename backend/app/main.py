import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routers import copilot, crm, health, meta, sources

logging.basicConfig(level=logging.INFO)


def _warm_up_models() -> None:
    """Load the embedding + reranker models once, so the first user query isn't slow."""
    from app.ingestion.embeddings import get_embedder
    from app.retrieval.reranker import get_reranker

    get_embedder().embed_query("warm up")
    get_reranker().score("warm up", ["warm up"])
    logging.getLogger(__name__).info("Embedding and reranker models loaded")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if get_settings().warmup_models:
        threading.Thread(target=_warm_up_models, daemon=True).start()
    yield


app = FastAPI(title="AI Operations Copilot", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

MULTIPART_OVERHEAD = 64 * 1024  # boundaries, headers and form fields around the file


@app.middleware("http")
async def reject_oversized_uploads(request: Request, call_next):
    """Refuse an upload by its Content-Length before the body is read: FastAPI parses (and
    spools) the multipart body before the route runs, so the route's own size check alone
    would still write the whole file to disk first."""
    if request.method == "POST" and request.url.path == "/api/sources":
        settings = request.app.dependency_overrides.get(get_settings, get_settings)()
        length = request.headers.get("content-length", "")
        if length.isdigit() and int(length) > settings.max_upload_bytes + MULTIPART_OVERHEAD:
            return JSONResponse(
                {"detail": f"File exceeds {settings.max_upload_bytes} bytes"},
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            )
    return await call_next(request)


app.include_router(health.router)
app.include_router(meta.router)
app.include_router(sources.router)
app.include_router(copilot.router)
app.include_router(crm.router)
