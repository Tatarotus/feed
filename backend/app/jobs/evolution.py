import logging

from app.database import SessionLocal
from app.services.mutation_engine import mutation_engine

logger = logging.getLogger("jobs.evolution")

async def run_semantic_evolution():
    """
    Background job to run the Semantic Evolution Engine:
    1. Telemetry validation: Score mutations, promote good ones, decay/kill failed ones.
    2. Evolve interests: Generate new mutations from active interests or promoted mutations.
    """
    logger.info("--- Starting Semantic Evolution Sweep ---")
    db = SessionLocal()
    try:
        # 1. Run telemetry processing first
        logger.info("Executing telemetry evaluation on active mutations...")
        mutation_engine.process_telemetry(db)

        # 2. Then generate new mutations
        logger.info("Executing interest evolution to generate new mutations...")
        await mutation_engine.evolve_interests(db)

        logger.info("--- Semantic Evolution Sweep Completed Safely ---")
    except Exception as e:
        logger.error(f"Error during semantic evolution sweep: {str(e)}")
    finally:
        db.close()
