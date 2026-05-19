from dotenv import load_dotenv
import os
from datetime import timedelta

load_dotenv()
class Config:
    DATABASE_URL = os.environ["DATABASE_URL"]
    FLASK_ENV = os.environ["FLASK_ENV"]
    JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]
    FRONTEND_URL = os.environ["FRONTEND_URL"]

    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(hours=12)