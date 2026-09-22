import mysql.connector
import os


def get_db_connection():

    connection = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        port=int(os.getenv("DB_PORT", 3306))
    )

    return connection


if __name__ == "__main__":

    connection = get_db_connection()

    if connection.is_connected():
        print("MySQL connection successful!")

    connection.close()