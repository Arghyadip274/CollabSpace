import asyncio
from src.database import connect_db, disconnect_db, db
from src.auth.jwt import create_access_token

async def get_tokens():
    await connect_db()
    users = await db.user.find_many(take=2)
    for u in users:
        print(f"{u.name}: {create_access_token(u.id)}")
    
    # We also need to create a document for testing in one of the workspaces
    ws = await db.workspace.find_first()
    if ws:
        # Check if doc exists
        doc = await db.document.find_first(where={"title": "Test Doc 1"})
        if not doc:
            doc = await db.document.create(
                data={
                    "title": "Test Doc 1",
                    "workspaceId": ws.id,
                    "creatorId": users[0].id,
                    "content": ""
                }
            )
        print(f"Document ID: {doc.id}")
        
    await disconnect_db()

if __name__ == "__main__":
    asyncio.run(get_tokens())
