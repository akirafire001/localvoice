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

    from .api.commands import bp as commands_bp
    from .api.guides import bp as guides_bp
    from .api.preferences import bp as prefs_bp
    from .api.trips import bp as trips_bp
    from .api.voices import bp as voices_bp

    for bp in (auth_bp, trips_bp, guides_bp, prefs_bp, voices_bp, commands_bp):
        app.register_blueprint(bp, url_prefix="/api/v1")

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.cli.command("init-db")
    def init_db_cmd():
        """Create tables (PostGIS extension included)."""
        create_schema(app)
        print("schema created")

    @app.cli.command("seed")
    def seed_cmd():
        """Load the draft curated stories for the PoC regions."""
        from .db import session_scope
        from .seed import curated

        with session_scope(app) as db:
            c, u = curated.load(db)
        print(f"curated stories: {c} created, {u} updated")

    from .worker import register as register_worker

    register_worker(app)

    @app.cli.command("drop-db")
    def drop_db_cmd():
        drop_schema(app)
        print("schema dropped")

    return app
