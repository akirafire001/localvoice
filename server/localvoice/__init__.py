import logging

from flask import Flask

from .config import Config
from .db import create_schema, drop_schema, init_engine
from .errors import register_error_handlers


def create_app(config=None):
    app = Flask(__name__)
    app.config["LV"] = config or Config()
    app.json.ensure_ascii = False
    logging.basicConfig(level=logging.INFO)
    init_engine(app)
    register_error_handlers(app)

    from .auth.routes import bp as auth_bp

    app.register_blueprint(auth_bp, url_prefix="/api/v1")

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.cli.command("init-db")
    def init_db_cmd():
        """Create tables (PostGIS extension included)."""
        create_schema(app)
        print("schema created")

    @app.cli.command("drop-db")
    def drop_db_cmd():
        drop_schema(app)
        print("schema dropped")

    return app
