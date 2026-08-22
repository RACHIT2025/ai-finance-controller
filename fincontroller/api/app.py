"""
FastAPI Application Entrypoint for FinController.
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fincontroller.api.routes import router
from fincontroller.core.config import settings

app = FastAPI(
    title="Razorpay AI Finance Controller",
    description="Settlement Reconciliation & Q&A Agent with Deterministic Matching Engine & Cryptographic Audit Trail",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(router, prefix="/api")

# Static UI files
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "static")
templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "templates")

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def serve_index():
    index_file = os.path.join(templates_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "FinController API is live. Access documentation at /docs"}
