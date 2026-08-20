"""
Seed script — creates reproducible test data.

Usage:
    cd apps/backend
    python scripts/seed.py

Creates:
    - alice@example.com  (password: Password1!)  → owner of "Acme HQ"
    - bob@example.com    (password: Password1!)  → member of "Acme HQ"
    - workspace: "Acme HQ"  (slug: acme-hq)
"""

import asyncio
import sys
from pathlib import Path

# Allow importing src.* from the backend root
sys.path.insert(0, str(Path(__file__).parent.parent))

import bcrypt
from prisma import Prisma


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

USERS = [
    {
        "email": "alice@example.com",
        "name": "Alice",
        "password": "Password1!",
    },
    {
        "email": "bob@example.com",
        "name": "Bob",
        "password": "Password1!",
    },
]

WORKSPACE = {
    "name": "Acme HQ",
    "slug": "acme-hq",
}


async def seed() -> None:
    db = Prisma()
    await db.connect()

    print("[SEED] Seeding database...")

    # Clean up existing seed data (idempotent)
    for u in USERS:
        existing = await db.user.find_unique(where={"email": u["email"]})
        if existing:
            await db.refreshtoken.delete_many(where={"userId": existing.id})
            await db.workspacemember.delete_many(where={"userId": existing.id})

    existing_ws = await db.workspace.find_unique(where={"slug": WORKSPACE["slug"]})
    if existing_ws:
        await db.workspacemember.delete_many(where={"workspaceId": existing_ws.id})
        await db.workspace.delete(where={"id": existing_ws.id})

    for u in USERS:
        existing = await db.user.find_unique(where={"email": u["email"]})
        if existing:
            await db.user.delete(where={"id": existing.id})

    # Create users
    created_users = []
    for u in USERS:
        user = await db.user.create(
            data={
                "email": u["email"],
                "name": u["name"],
                "passwordHash": _hash(u["password"]),
            }
        )
        created_users.append(user)
        print(f"   [OK]  Created user: {user.name} <{user.email}>  (id: {user.id})")

    alice, bob = created_users

    # Create workspace with Alice as owner
    workspace = await db.workspace.create(
        data={
            "name": WORKSPACE["name"],
            "slug": WORKSPACE["slug"],
            "ownerId": alice.id,
            "members": {
                "create": {
                    "userId": alice.id,
                    "role": "OWNER",
                }
            },
        }
    )
    print(f"   [OK]  Created workspace: {workspace.name}  (slug: {workspace.slug})")

    # Invite Bob as MEMBER
    await db.workspacemember.create(
        data={
            "workspaceId": workspace.id,
            "userId": bob.id,
            "role": "MEMBER",
        }
    )
    print(f"   [OK]  Added Bob as MEMBER of {workspace.name}")

    await db.disconnect()
    print("\nSeed complete!")
    print("\nTest credentials:")
    print("  alice@example.com / Password1!  (workspace owner)")
    print("  bob@example.com   / Password1!  (workspace member)")
    print(f"  Workspace ID: {workspace.id}")


if __name__ == "__main__":
    asyncio.run(seed())
