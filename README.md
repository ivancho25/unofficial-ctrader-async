# unofficial-ctrader-async

A minimal, modern Python library for connecting to the [cTrader Open API](https://help.ctrader.com/open-api/) using `asyncio`.

## Why

The official cTrader Open API SDK is built on [Twisted](https://twisted.org/), a framework predating Python's native `asyncio`. This library provides a clean alternative compatible with modern async Python.

## What it does

- Opens and maintains a persistent SSL/TCP connection to the cTrader API
- Authenticates the application and a trading account
- Listens for and dispatches incoming `ProtoOAExecutionEvent` messages in real time
- Sends periodic heartbeats to keep the connection alive
- Closes cleanly on exit

It does not interpret, store, or act on the data it receives. That is the responsibility of the application built on top of it.

## Requirements

- Python 3.12+
- Your own cTrader Open API credentials, obtained by registering an application
  at [openapi.ctrader.com](https://openapi.ctrader.com)

**Runtime dependencies:**
```
pip install protobuf python-dotenv
```

**Only needed to recompile `.proto` files** (pre-compiled `_pb2.py` files are
included in `proto/`):
```
pip install grpcio-tools
```

## Configuration

Create a `.env` file in the project root:

```
CLIENT_ID=your_client_id
CLIENT_SECRET=your_client_secret
ACCESS_TOKEN=your_access_token
ACCOUNT_ID=your_account_id
CTRADER_HOST=demo.ctraderapi.com
CTRADER_PORT=5035
```

For live accounts, set `CTRADER_HOST=live.ctraderapi.com`.

Never commit this file. It is excluded by `.gitignore`.

## Usage

This is a minimal connection example. To handle execution events, subclass
`CTraderClient` and override `_on_execution`:

```python
import asyncio
from ctrader_async.connection import CTraderClient
from ctrader_async.proto import OpenApiMessages_pb2 as msg

class MyClient(CTraderClient):
    async def _on_execution(self, event: msg.ProtoOAExecutionEvent) -> None:
        print(f"Event type: {event.executionType}")
        print(f"Order: {event.order}")

async def main():
    client = MyClient()
    await client.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
```

## Proto files

The `.proto` message definitions in `proto_src/` are the official Spotware Open API message definitions, used here unmodified under their original license.

© 2021 Spotware Systems Ltd — MIT License  
Source: [github.com/spotware/openapi-proto-messages](https://github.com/spotware/openapi-proto-messages)

## Legal

Use of this library requires compliance with the [cTrader Open API Terms of Use](https://help.ctrader.com/open-api/). The user is solely responsible for ensuring that any application built with this library adheres to those terms, including all obligations regarding trader data, GDPR, and fair use of API resources.

This library is provided as is, with no warranties of any kind.

## License

MIT License — see [LICENSE](LICENSE) for details.
