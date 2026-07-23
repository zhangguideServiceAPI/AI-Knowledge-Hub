from app.db.session import is_database_ready


def is_application_ready() -> bool:
    return is_database_ready()
