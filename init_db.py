"""Create tables and seed the same data used by the FastAPI startup hook."""

from database import Base, SessionLocal, engine
from app import seed_database


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    seed_database()
    print("Database is ready")
