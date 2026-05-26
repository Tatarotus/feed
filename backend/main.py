from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import engine, Base
from app import models
from app.routes import channels, feed, queue, search, interests, debug

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Set all CORS enabled origins
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

def init_db():
    """Ensure pgvector extension is created and all tables are initialized."""
    print("Initializing database...")
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()
    # Create all tables defined in models.py
    Base.metadata.create_all(bind=engine)
    
    # Run auto-migration to add columns to channels if they don't exist
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE channels ADD COLUMN IF NOT EXISTS is_subscribed BOOLEAN DEFAULT TRUE;"))
            conn.execute(text("ALTER TABLE channels ADD COLUMN IF NOT EXISTS thumbnail_url VARCHAR(512);"))
            conn.commit()
        except Exception as e:
            print(f"Auto-migration note: {e}")
            
    print("Database tables initialized successfully!")

@app.on_event("startup")
def startup_event():
    init_db()

# Mount all modular routers under settings.API_V1_STR prefix (/api)
app.include_router(channels.router, prefix=settings.API_V1_STR)
app.include_router(feed.router, prefix=settings.API_V1_STR)
app.include_router(queue.router, prefix=settings.API_V1_STR)
app.include_router(search.router, prefix=settings.API_V1_STR)
app.include_router(interests.router, prefix=settings.API_V1_STR)
app.include_router(debug.router, prefix=settings.API_V1_STR)

@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy", "project": settings.PROJECT_NAME}
