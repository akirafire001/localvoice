from flask import jsonify


class ApiError(Exception):
    """Error rendered as {code, message, details} (api-design 共通)."""

    def __init__(self, status, code, message, details=None, headers=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}
        self.headers = headers or {}


def bad_request(message="invalid request", details=None, code="invalid_request"):
    return ApiError(400, code, message, details)


def unauthorized(message="authentication required", code="unauthorized"):
    return ApiError(401, code, message)


def forbidden(message="forbidden", code="forbidden"):
    return ApiError(403, code, message)


def not_found(message="not found", code="not_found"):
    return ApiError(404, code, message)


def conflict(message="conflict", code="conflict", details=None):
    return ApiError(409, code, message, details)


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def _api_error(e):
        resp = jsonify({"code": e.code, "message": e.message, "details": e.details})
        resp.status_code = e.status
        for k, v in e.headers.items():
            resp.headers[k] = v
        return resp

    @app.errorhandler(404)
    def _404(e):
        return jsonify({"code": "not_found", "message": "not found", "details": {}}), 404

    @app.errorhandler(405)
    def _405(e):
        return (
            jsonify({"code": "method_not_allowed", "message": "method not allowed", "details": {}}),
            405,
        )

    @app.errorhandler(500)
    def _500(e):
        return jsonify({"code": "internal_error", "message": "internal error", "details": {}}), 500
