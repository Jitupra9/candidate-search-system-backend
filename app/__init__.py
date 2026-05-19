from flask import Flask
from flask_cors import CORS

from app.config import Config


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(
        app,
        origins=[app.config["FRONTEND_URL"]],
        supports_credentials=True
    )
    return app