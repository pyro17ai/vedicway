from __future__ import annotations

from .content_store import ContentDatabase


def main() -> None:
    database = ContentDatabase()
    database.ping(require_migrations=True)
    created = database.bootstrap_admin_from_environment()
    print("admin_created" if created else "admin_already_exists")


if __name__ == "__main__":
    main()
