import asyncio
import ssl
import os
from dotenv import load_dotenv
from ctrader_async.proto import OpenApiMessages_pb2 as msg
from ctrader_async.proto import OpenApiCommonMessages_pb2 as common
from ctrader_async import protocol

load_dotenv(override=True)

HOST          = os.getenv("CTRADER_HOST", "demo.ctraderapi.com")
PORT          = int(os.getenv("CTRADER_PORT", 5035))
CLIENT_ID     = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
ACCESS_TOKEN  = os.getenv("ACCESS_TOKEN")
ACCOUNT_ID    = int(os.getenv("ACCOUNT_ID"))

HEARTBEAT_INTERVAL = 10

PT_APP_AUTH_REQ     = 2100
PT_APP_AUTH_RES     = 2101
PT_ACCOUNT_AUTH_REQ = 2102
PT_ACCOUNT_AUTH_RES = 2103
PT_EXECUTION_EVENT  = 2126
PT_HEARTBEAT        = 51

class CTraderClient:

    def __init__(self):
        self.reader   = None
        self.writer   = None
        self._running = False

    async def connect(self):
        ctx = ssl.create_default_context()
        self.reader, self.writer = await asyncio.open_connection(
            HOST, PORT, ssl=ctx
        )
        self._running = True
        print(f"✓ Conectado a {HOST}:{PORT}")

    async def _send(self, payload_type: int, message) -> None:
        env = protocol.wrap(payload_type, message.SerializeToString())
        await protocol.write_message(self.writer, env)

    async def authenticate_app(self):
        req = msg.ProtoOAApplicationAuthReq()
        req.clientId     = CLIENT_ID
        req.clientSecret = CLIENT_SECRET
        await self._send(PT_APP_AUTH_REQ, req)
        print("→ ApplicationAuthReq enviado")

    async def authenticate_account(self):
        req = msg.ProtoOAAccountAuthReq()
        req.ctidTraderAccountId = ACCOUNT_ID
        req.accessToken         = ACCESS_TOKEN
        await self._send(PT_ACCOUNT_AUTH_REQ, req)
        print("→ AccountAuthReq enviado")

    async def _heartbeat(self):
        while self._running:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            hb = common.ProtoHeartbeatEvent()
            await protocol.write_message(
                self.writer,
                protocol.wrap(PT_HEARTBEAT, hb.SerializeToString())
            )
            print("♥ heartbeat")

    async def _dispatch(self, envelope: common.ProtoMessage) -> None:
        pt = envelope.payloadType
        print(f"← payloadType={pt}")

        if pt == PT_APP_AUTH_RES:
            print("✓ App autenticada")
            await self.authenticate_account()

        elif pt == PT_ACCOUNT_AUTH_RES:
            print("✓ Cuenta autenticada — escuchando eventos")

        elif pt == PT_EXECUTION_EVENT:
            event = msg.ProtoOAExecutionEvent()
            event.ParseFromString(envelope.payload)
            await self._on_execution(event)

        elif pt == PT_HEARTBEAT:
            pass

    async def _on_execution(self, event: msg.ProtoOAExecutionEvent) -> None:
        print(f"⚡ ExecutionEvent: executionType={event.executionType}")
        print(f"   order: {event.order}")

    async def listen(self):
        while self._running:
            try:
                data     = await protocol.read_message(self.reader)
                envelope = protocol.unwrap(data)
                await self._dispatch(envelope)
            except asyncio.IncompleteReadError:
                print("✗ Conexión cerrada por el servidor")
                self._running = False

    async def disconnect(self):
        self._running = False
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
        print("\n✓ Desconectado limpiamente")

    async def run(self):
        try:
            await self.connect()
            await self.authenticate_app()
            await asyncio.gather(
                self.listen(),
                self._heartbeat()
            )
        except asyncio.CancelledError:
            pass
        finally:
            await self.disconnect()
