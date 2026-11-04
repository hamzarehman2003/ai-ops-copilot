import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

app.include_router(health.router)
app.include_router(meta.router)
app.include_router(sources.router)
app.include_router(copilot.router)
app.include_router(crm.router)
