import os
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "driver": "{ODBC Driver 18 for SQL Server}",
    "server": os.getenv("DB_SERVER"),
    "database": os.getenv("DB_NAME"),
    "trusted_connection": "yes",
    "trust_server_certificate": "yes"
}

def get_connection_string():
    return (
        f"DRIVER={DB_CONFIG['driver']};"
        f"SERVER={DB_CONFIG['server']};"
        f"DATABASE={DB_CONFIG['database']};"
        f"Trusted_Connection={DB_CONFIG['trusted_connection']};"
        f"TrustServerCertificate={DB_CONFIG['trust_server_certificate']};"
    )