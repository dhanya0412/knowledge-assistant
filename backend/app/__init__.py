from flask import Flask
from flask_jwt_extended import JWTManager

from app.config import Config
from app.routes import register_routes
from app.database import init_db

jwt = JWTManager()


def create_app():
    app = Flask(__name__)

    app.config.from_object(Config)
    jwt.init_app(app)
    init_db(app)
    register_routes(app)

    return app