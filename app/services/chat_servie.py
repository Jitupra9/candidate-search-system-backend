
from sqlalchemy.ext.asyncio import AsyncSession



def ask_Api_Service(db:AsyncSession,body):
    if not body:
        print("no payload found")
    