"""VedicWay chart-result backend."""


def create_app():
    """Import the ASGI application lazily so calculation modules stay standalone."""
    from .main import create_app as _create_app

    return _create_app()


__all__ = ["create_app"]
