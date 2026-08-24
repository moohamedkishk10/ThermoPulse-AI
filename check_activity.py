import asyncio
from fortyguard import FortyGuardClient

ACTIVITY_ID = "1427f0a6-29a9-4dfb-8caf-c8269ab185f6"

async def main():
    async with FortyGuardClient() as client:
        status = await client.check_status(ACTIVITY_ID)
        print(status)

asyncio.run(main())