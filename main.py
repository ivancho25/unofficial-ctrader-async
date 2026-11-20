import asyncio
from ctrader_async.connection import CTraderClient

async def main():
    client = CTraderClient()
    await client.run()

if __name__ == "__main__":
    asyncio.run(main())
