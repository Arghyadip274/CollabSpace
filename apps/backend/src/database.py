"""
Prisma database client — async singleton with lifespan management.
"""

from prisma import Prisma

db = Prisma()


async def connect_db() -> None:
    """Connect the Prisma client. Called on app startup."""
    if not db.is_connected():
        await db.connect()


async def disconnect_db() -> None:
    """Disconnect the Prisma client. Called on app shutdown."""
    if db.is_connected():
        await db.disconnect()
