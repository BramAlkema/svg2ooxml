"""FastAPI application entry point for svg2ooxml-export service."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.svg2ooxml.api.routes.export import router as export_router
from src.svg2ooxml.api.middleware import RateLimiter, RateLimitMiddleware


RATE_LIMIT = int(os.getenv("SVG2OOXML_RATE_LIMIT", "60"))
RATE_WINDOW_SECONDS = int(os.getenv("SVG2OOXML_RATE_WINDOW", "60"))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    logger.info("Starting svg2ooxml-export service")
    logger.info(f"Project ID: {os.getenv('GCP_PROJECT', 'not set')}")
    logger.info(f"Environment: {os.getenv('ENVIRONMENT', 'production')}")

    yield

    # Shutdown
    logger.info("Shutting down svg2ooxml-export service")


# Create FastAPI app
app = FastAPI(
    title="svg2ooxml Export API",
    description="Figma SVG to PowerPoint/Google Slides conversion service",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS for Figma plugin
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.figma.com",
        "https://figma.com",
        # Add localhost for development
        "http://localhost:*",
        "http://127.0.0.1:*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Basic per-client rate limiting middleware
rate_limiter = RateLimiter(limit=RATE_LIMIT, window_seconds=RATE_WINDOW_SECONDS)
app.add_middleware(RateLimitMiddleware, limiter=rate_limiter)

# Include routers
app.include_router(export_router, prefix="/api/v1", tags=["export"])


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "service": "svg2ooxml-export",
        "status": "healthy",
        "version": "0.1.0",
    }


@app.get("/health")
async def health():
    """Kubernetes/Cloud Run health check endpoint."""
    return JSONResponse(
        content={"status": "healthy"},
        status_code=200,
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True,
    )
