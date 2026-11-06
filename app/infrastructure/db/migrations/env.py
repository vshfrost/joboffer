from alembic import context

from infrastructure.db.schema import metadata

# З'єднання завжди передає infrastructure.db.migrate:
# оточення читає лише bootstrap (`python -m bootstrap.migrate`).
connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError(
        "Міграції запускаються через `python -m bootstrap.migrate`, а не `alembic upgrade`."
    )
context.configure(connection=connection, target_metadata=metadata)
with context.begin_transaction():
    context.run_migrations()
