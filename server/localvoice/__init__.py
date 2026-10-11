import logging

import click
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

    from .landing import bp as landing_bp

    app.register_blueprint(landing_bp)

    from .web import bp as web_bp

    app.register_blueprint(web_bp)

    from .auth.routes import bp as auth_bp

    from .api.commands import bp as commands_bp
    from .api.external_gen import bp as external_gen_bp
    from .api.guides import bp as guides_bp
    from .api.preferences import bp as prefs_bp
    from .api.trips import bp as trips_bp
    from .api.voices import bp as voices_bp

    for bp in (auth_bp, trips_bp, guides_bp, prefs_bp, voices_bp, commands_bp, external_gen_bp):
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

    @app.cli.command("rewrite-stories")
    @click.option("--cell", default=None, help="Only stories of this geohash cell.")
    @click.option("--limit", type=int, default=None, help="Rewrite at most this many stories.")
    @click.option("--force", is_flag=True, help="Also rewrite stories that already have a storytelling version.")
    @click.option("--dry-run", is_flag=True, help="Print the rewrites without saving them (the LLM is still called).")
    def rewrite_stories_cmd(cell, limit, force, dry_run):
        """Give stories already in the database a spoken version written with the storytelling techniques."""
        from .db import session_scope
        from .services.llm import get_llm
        from .services.rewrite import rewrite_all

        llm = get_llm()
        if llm is None:
            raise click.ClickException("LLM is disabled: set LLM_PROVIDER and its API key")
        with session_scope(app) as db:
            rewrite_all(db, llm, cell=cell, limit=limit, force=force, dry_run=dry_run, echo=click.echo)

    @app.cli.command("generate-global-stories")
    @click.option("--themes", type=int, default=None, help="Research at most this many themes (default: per-job count).")
    def generate_global_cmd(themes):
        """Write stories that hold anywhere in the world (told while a new place's stories are being written)."""
        from .db import session_scope
        from .services.knowledge_gen import generate_global
        from .services.llm import LLMError

        with session_scope(app) as db:
            try:
                created, more = generate_global(db, themes=themes, echo=click.echo)
            except LLMError as e:
                raise click.ClickException(f"generation failed: {e}")
        click.echo(f"global stories: {created} created" + ("; themes left, run again for more" if more else ""))

    from .worker import register as register_worker

    register_worker(app)

    @app.cli.command("drop-db")
    def drop_db_cmd():
        drop_schema(app)
        print("schema dropped")

    return app
