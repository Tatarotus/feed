import logging
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.jobs.ingest import run_ingestion
from app.jobs.discovery import run_discovery
from app.jobs.process_chunks import run_chunk_processing
from app.jobs.process_vectors import run_vector_processing
from app.jobs.cleanup import run_cleanup_and_tuning

# Setup centralized logging layout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("jobs.coordinator")

async def run_pipeline_sweep():
    """
    Sequentially runs the full pipeline stages:
    1. Ingestion of new feeds.
    1.5. Dynamic out-of-network discovery.
    2. Transcription & Chunking of pending text.
    3. Bulk vector generation and clickbait classification.
    """
    logger.info("--- Starting Full Pipeline Sweep ---")
    try:
        # Step 1: Ingest fresh videos from subscribed channels
        await run_ingestion()
        
        # Step 1.5: Discover fresh out-of-network content based on interest topics
        await run_discovery()
        
        # Step 2: Transcript crawl & chunking for all pending videos
        await run_chunk_processing()
        
        # Step 3: Embed vectors & clickbait check (Directly await async method)
        await run_vector_processing()
        
        logger.info("--- Pipeline Sweep Completed Safely ---")
    except Exception as e:
        logger.error(f"Error during coordinated pipeline sweep: {str(e)}")

async def run_maintenance_sweep():
    """Runs telemetry processing to auto-tune preferences and deletes expired unseen content."""
    logger.info("--- Starting Database Maintenance Curation ---")
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, run_cleanup_and_tuning)
        logger.info("--- Database Maintenance Completed Safely ---")
    except Exception as e:
        logger.error(f"Error during maintenance sweep: {str(e)}")

def main():
    scheduler = AsyncIOScheduler()
    
    # 1. Ingestion of subscribed feeds: scheduled every 15 minutes
    scheduler.add_job(
        run_ingestion, 
        'interval', 
        minutes=15, 
        id='ingestion_job', 
        replace_existing=True
    )
    
    # 2. Dynamic discovery: scheduled every 30 minutes (to avoid heavy API usage)
    scheduler.add_job(
        run_discovery, 
        'interval', 
        minutes=30, 
        id='discovery_job', 
        replace_existing=True
    )
    
    # 3. Transcript crawl & chunking: scheduled every 2 minutes for continuous, rapid throughput
    scheduler.add_job(
        run_chunk_processing, 
        'interval', 
        minutes=2, 
        id='chunk_processing_job', 
        replace_existing=True
    )
    
    # 4. Bulk vector generation & embedding: scheduled every 2 minutes for real-time indexing
    scheduler.add_job(
        run_vector_processing, 
        'interval', 
        minutes=2, 
        id='vector_processing_job', 
        replace_existing=True
    )
    
    # 5. Maintenance / Telemetry auto-tuning: scheduled every 60 minutes
    scheduler.add_job(
        run_maintenance_sweep,
        'interval',
        minutes=60,
        id='database_maintenance_job',
        replace_existing=True
    )
    
    # Inject one-shot triggers to kickstart processing immediately on service boot
    scheduler.add_job(run_ingestion, id='boot_ingest_trigger')
    scheduler.add_job(run_chunk_processing, id='boot_chunk_trigger')
    scheduler.add_job(run_vector_processing, id='boot_vector_trigger')
    
    logger.info("SignalFeed Coordinated jobs worker scheduler successfully running with independent concurrent threads!")
    scheduler.start()
    
    # Keep the async event loop thread process active
    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        logger.info("SignalFeed background coordinator shutting down...")

if __name__ == "__main__":
    main()

