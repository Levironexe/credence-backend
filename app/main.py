from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.routers import auth, chat, documents, vote, api_compat, files, health, applicants
from app.database import engine, Base
import uvicorn
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name, debug=settings.debug)

# CORS configuration - allow both localhost and production URLs
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:3000",
        "http://localhost:3001",  # Next.js sometimes uses 3001
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "https://credence-ai-chat.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Include routers
app.include_router(health.router)  # Health checks
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(vote.router)
app.include_router(files.router)
app.include_router(applicants.router)  # Applicant profiles
app.include_router(api_compat.router)  # Compatibility routes

# Serve static files (SHAP plots, etc.)
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.on_event("startup")
async def startup():
    """Initialize database tables on startup"""
    logger.info("🚀 Starting Credence AI Backend...")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.warning(f"⚠️ Database initialization failed: {e}")
        logger.warning("App will start but database operations will fail until DATABASE_URL is configured")


@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Credence AI Backend", "status": "running"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)