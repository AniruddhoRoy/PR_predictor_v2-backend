from sqlalchemy.orm import Session

from database import engine, SessionLocal, Base
from models import User


def init_database():

    # Create tables if missing
    Base.metadata.create_all(bind=engine)


    db: Session = SessionLocal()

    # Check existing data
    user_count = db.query(User).count()


    if user_count == 0:

        demo_users = [
            User(
                name="John",
                email="john@test.com"
            ),

            User(
                name="Alice",
                email="alice@test.com"
            )
        ]


        db.add_all(demo_users)
        db.commit()

        print("Demo data inserted")

    else:
        print("Database already initialized")


    db.close()