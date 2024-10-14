from app.db.db_setup import SessionLocal


async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        await db.close()
