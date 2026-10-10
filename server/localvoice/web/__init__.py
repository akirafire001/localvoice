"""Browser console.

/login and /account are for every signed-in user. /admin is the operator dashboard
(generation volume, languages, and the world map). Screens for managing users will
be added under /admin later; they are not part of this blueprint yet.
"""
from flask import Blueprint

bp = Blueprint("web", __name__)

from . import routes  # noqa: E402,F401
