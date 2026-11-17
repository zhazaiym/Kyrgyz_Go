"""What the application lends to the agent. ML imports nothing from mysite:
the application calls configure() once and the agent reads the result here."""

from datetime import date


def _ignore(*_):
    return None


class _Application:
    sessions = None  # opens a database session
    models = None  # catalogue ORM models (the mysite.database.models module)
    today = staticmethod(date.today)  # the company's calendar date
    record_ai_call = staticmethod(_ignore)  # (operation, outcome, seconds)
    record_ai_tokens = staticmethod(_ignore)  # (operation, tokens)


app = _Application()


def configure(*, sessions, models, today, record_ai_call, record_ai_tokens):
    app.sessions = sessions
    app.models = models
    app.today = today
    app.record_ai_call = record_ai_call
    app.record_ai_tokens = record_ai_tokens


def SessionLocal():
    """The single database entry point of the agent and its tools."""
    if app.sessions is None:
        raise RuntimeError('ML.runtime.configure() has not been called by the application')
    return app.sessions()
