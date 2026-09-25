import mysql.connector
import os


def get_db_connection():
    connection = mysql.connector.connect(
        host="sql.freedb.tech",
        user="u_oFaCoZ",
        password="KXFMJB4FVSwo",
        database="freedb_rkfgn8Fz",
        port=3306
    )

    return connection


if __name__ == "__main__":

    connection = get_db_connection()

    if connection.is_connected():
        print("MySQL connection successful!")

    connection.close()