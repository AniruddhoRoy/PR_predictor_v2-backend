import pymysql

MYSQL_HOST = "localhost"
MYSQL_PORT = 5050
MYSQL_USER = "root"
MYSQL_PASSWORD = "rootpassword"

DATABASE_NAME = "fastapi_demo"


def create_database():

    try:
        # Connect without selecting database
        connection = pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD
        )

        cursor = connection.cursor()

        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS {DATABASE_NAME}"
        )

        print(f"Database '{DATABASE_NAME}' created or already exists.")

        cursor.close()
        connection.close()

    except Exception as e:
        print("Error:", e)


if __name__ == "__main__":
    create_database()