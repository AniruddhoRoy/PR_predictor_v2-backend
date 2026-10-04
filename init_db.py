"""Create tables and seed the same data used by the FastAPI startup hook."""

from app import startup_event


if __name__ == "__main__":
    startup_event()
    print("Database is ready")
