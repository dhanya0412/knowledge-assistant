from flask import Flask

from app.config import Config
from app.routes import register_routes
from app.database import init_db

def create_app():
    app = Flask(__name__)

    app.config.from_object(Config)
    init_db(app)
    register_routes(app)

    return app