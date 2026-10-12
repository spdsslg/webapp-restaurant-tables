from flask import Flask


def create_app(test_config=None):
    """Create an application with environment settings and optional test overrides."""
    app = Flask(__name__)
    app.config.from_mapping(
        RESTAURANT_NAME="Restaurant", RESTAURANT_TIMEZONE="Europe/Warsaw"
    )
    app.config.from_prefixed_env()
    if test_config is not None:
        app.config.update(test_config)

    from .main import bp

    app.register_blueprint(bp)
    return app
