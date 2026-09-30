"""Optional helper for creating a MySQL database before SQLAlchemy connects."""

import os

import pymysql


MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "5050"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "rootpassword")
DATABASE_NAME = os.getenv("MYSQL_DATABASE", "fastapi_demo")


def create_database():
    connection = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD)
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{DATABASE_NAME}`")
        connection.commit()
        print(f"Database '{DATABASE_NAME}' is ready")
    finally:
        connection.close()


if __name__ == "__main__":
    create_database()
