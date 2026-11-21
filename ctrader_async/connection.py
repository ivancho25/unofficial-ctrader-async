import asyncio
import os
import ssl

from dotenv import load_dotenv

from ctrader_async.proto import OpenApiMessages_pb2 as msg
from ctrader_async.proto import OpenApiCommonMessages_pb2 as common
from ctrader_async import protocol


load_dotenv(override=True)

HOST = os.getenv("CTRADER_HOST", "demo.ctraderapi.com")
PORT = int(os.getenv("CTRADER_PORT", 5035))
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCOUNT_ID = int(os.getenv("ACCOUNT_ID"))

HEARTBEAT_INTERVAL = 10

# cTrader Open API payload types
PT_APP_AUTH_REQ = 2100
PT_APP_AUTH_RES = 2101
PT_ACCOUNT_AUTH_REQ = 2102
PT_ACCOUNT_AUTH_RES = 2103
PT_SYMBOLS_LIST_REQ = 2114
PT_SYMBOLS_LIST_RES = 2115
PT_SYMBOL_BY_ID_REQ = 2116
PT_SYMBOL_BY_ID_RES = 2117
PT_EXECUTION_EVENT = 2126
PT_ERROR_RES = 2142
PT_HEARTBEAT = 51


def _scaled_money(raw_value: int, digits: int | None) -> str:
    """Convert cTrader monetary integer to its decimal representation."""
    if digits is None:
        return f"{raw_value} (moneyDigits unavailable)"
    return f"{raw_value / (10 ** digits):.8f}".rstrip("0").rstrip(".")


class CTraderClient:

    def __init__(self):
        self.reader = None
        self.writer = None
        self._running = False
        self._symbols_requested = False
        self._symbol_names_by_id = {}

    async def connect(self):
        ctx = ssl.create_default_context()
        self.reader, self.writer = await asyncio.open_connection(
            HOST, PORT, ssl=ctx
        )
        self._running = True
        print(f"✓ Conectado a {HOST}:{PORT}")

    async def _send(self, payload_type: int, message) -> None:
        envelope = protocol.wrap(payload_type, message.SerializeToString())
        await protocol.write_message(self.writer, envelope)

    async def authenticate_app(self):
        req = msg.ProtoOAApplicationAuthReq()
        req.clientId = CLIENT_ID
        req.clientSecret = CLIENT_SECRET
        await self._send(PT_APP_AUTH_REQ, req)
        print("→ ApplicationAuthReq enviado")

    async def authenticate_account(self):
        req = msg.ProtoOAAccountAuthReq()
        req.ctidTraderAccountId = ACCOUNT_ID
        req.accessToken = ACCESS_TOKEN
        await self._send(PT_ACCOUNT_AUTH_REQ, req)
        print("→ AccountAuthReq enviado")

    async def request_symbols(self):
        """Request the account's symbol catalogue once after account auth."""
        if self._symbols_requested:
            return

        req = msg.ProtoOASymbolsListReq()
        req.ctidTraderAccountId = ACCOUNT_ID
        req.includeArchivedSymbols = False
        await self._send(PT_SYMBOLS_LIST_REQ, req)
        self._symbols_requested = True
        print("→ ProtoOASymbolsListReq enviado")

    async def request_symbol_details(self, symbol_ids):
        """Request full specifications for the selected symbol IDs."""
        ids = list(dict.fromkeys(int(symbol_id) for symbol_id in symbol_ids))
        if not ids:
            print("! No se encontraron símbolos BTC para consultar")
            return

        req = msg.ProtoOASymbolByIdReq()
        req.ctidTraderAccountId = ACCOUNT_ID
        req.symbolId.extend(ids)
        await self._send(PT_SYMBOL_BY_ID_REQ, req)
        print(f"→ ProtoOASymbolByIdReq enviado para {len(ids)} símbolo(s)")

    async def _heartbeat(self):
        while self._running:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            if not self._running or self.writer is None:
                break
            heartbeat = common.ProtoHeartbeatEvent()
            await protocol.write_message(
                self.writer,
                protocol.wrap(PT_HEARTBEAT, heartbeat.SerializeToString())
            )
            print("♥ heartbeat")

    async def _dispatch(self, envelope: common.ProtoMessage) -> None:
        payload_type = envelope.payloadType
        print(f"← payloadType={payload_type}")

        if payload_type == PT_APP_AUTH_RES:
            print("✓ App autenticada")
            await self.authenticate_account()

        elif payload_type == PT_ACCOUNT_AUTH_RES:
            print("✓ Cuenta autenticada — escuchando eventos")
            await self.request_symbols()

        elif payload_type == PT_SYMBOLS_LIST_RES:
            response = msg.ProtoOASymbolsListRes()
            response.ParseFromString(envelope.payload)
            await self._on_symbols_list(response)

        elif payload_type == PT_SYMBOL_BY_ID_RES:
            response = msg.ProtoOASymbolByIdRes()
            response.ParseFromString(envelope.payload)
            self._on_symbol_details(response)

        elif payload_type == PT_EXECUTION_EVENT:
            event = msg.ProtoOAExecutionEvent()
            event.ParseFromString(envelope.payload)
            await self._on_execution(event)

        elif payload_type == PT_ERROR_RES:
            error = msg.ProtoOAErrorRes()
            error.ParseFromString(envelope.payload)
            description = error.description if error.HasField("description") else ""
            print(f"✗ cTrader error: {error.errorCode} {description}")
            if error.HasField("retryAfter"):
                print(f"  retryAfter: {error.retryAfter} segundos")

        elif payload_type == PT_HEARTBEAT:
            pass

        else:
            print(f"! Payload no gestionado: {payload_type}")

    async def _on_symbols_list(self, response: msg.ProtoOASymbolsListRes):
        matches = []
        print(f"✓ Catálogo recibido: {len(response.symbol)} símbolos")

        for symbol in response.symbol:
            name = symbol.symbolName if symbol.HasField("symbolName") else ""
            if "BTC" in name.upper():
                matches.append(symbol)
                self._symbol_names_by_id[symbol.symbolId] = name
                enabled = (
                    symbol.enabled if symbol.HasField("enabled") else "no informado"
                )
                print(
                    f"  BTC candidato: {name} | symbolId={symbol.symbolId} "
                    f"| enabled={enabled}"
                )

        if not matches:
            print("! El catálogo no contiene nombres con 'BTC'.")
            print("  Si operaste otro criptoactivo, indícame el símbolo exacto.")
            return

        await self.request_symbol_details(symbol.symbolId for symbol in matches)

    def _on_symbol_details(self, response: msg.ProtoOASymbolByIdRes):
        print(f"✓ Especificaciones completas recibidas: {len(response.symbol)}")

        for symbol in response.symbol:
            name = self._symbol_names_by_id.get(symbol.symbolId, "nombre no disponible")
            print(f"\n--- ESPECIFICACIONES: {name} ---")
            print(f"symbolId: {symbol.symbolId}")
            print(f"digits: {symbol.digits}")
            print(f"pipPosition: {symbol.pipPosition}")

            for field in (
                "minVolume",
                "maxVolume",
                "stepVolume",
                "lotSize",
                "measurementUnits",
                "preciseTradingCommissionRate",
                "preciseMinCommission",
                "commissionType",
                "minCommissionAsset",
            ):
                if symbol.HasField(field):
                    print(f"{field}: {getattr(symbol, field)}")

            if symbol.HasField("lotSize") and symbol.lotSize:
                print(
                    "Conversión informativa: volume/lotSize = "
                    "volumen en lotes (ambos campos en escala de centésimas)"
                )

    async def _on_execution(self, event: msg.ProtoOAExecutionEvent) -> None:
        print(f"\n⚡ ExecutionEvent: executionType={event.executionType}")

        if event.HasField("order"):
            order = event.order
            print("  ORDER")
            print(f"    orderId: {order.orderId}")
            print(f"    orderType: {order.orderType}")
            print(f"    orderStatus: {order.orderStatus}")
            if order.HasField("executionPrice"):
                print(f"    executionPrice: {order.executionPrice}")
            if order.HasField("executedVolume"):
                print(f"    executedVolume: {order.executedVolume}")
                print(f"    executedVolume (unidades): {order.executedVolume / 100:.2f}")
            if order.HasField("closingOrder"):
                print(f"    closingOrder: {order.closingOrder}")
            if order.HasField("positionId"):
                print(f"    positionId: {order.positionId}")
            if order.HasField("stopPrice"):
                print(f"    stopPrice: {order.stopPrice}")
            if order.HasField("limitPrice"):
                print(f"    limitPrice: {order.limitPrice}")

        if event.HasField("deal"):
            deal = event.deal
            print("  DEAL")
            for field in (
                "dealId",
                "orderId",
                "positionId",
                "symbolId",
                "volume",
                "filledVolume",
                "tradeSide",
                "dealStatus",
                "executionPrice",
                "executionTimestamp",
                "commission",
                "moneyDigits",
            ):
                if deal.HasField(field):
                    print(f"    {field}: {getattr(deal, field)}")

            if deal.HasField("volume"):
                print(f"    volume (unidades): {deal.volume / 100:.2f}")
            if deal.HasField("filledVolume"):
                print(f"    filledVolume (unidades): {deal.filledVolume / 100:.2f}")

            if deal.HasField("commission"):
                digits = deal.moneyDigits if deal.HasField("moneyDigits") else None
                print(
                    "    commission (escalada): "
                    f"{_scaled_money(deal.commission, digits)}"
                )

            if deal.HasField("closePositionDetail"):
                detail = deal.closePositionDetail
                digits = (
                    detail.moneyDigits
                    if detail.HasField("moneyDigits")
                    else (deal.moneyDigits if deal.HasField("moneyDigits") else None)
                )
                print("  CLOSE POSITION DETAIL")
                print(f"    entryPrice: {detail.entryPrice}")
                print(f"    moneyDigits: {digits}")

                for field in (
                    "grossProfit",
                    "swap",
                    "commission",
                    "pnlConversionFee",
                    "balance",
                    "closedVolume",
                ):
                    if detail.HasField(field):
                        raw = getattr(detail, field)
                        print(f"    {field} (raw): {raw}")
                        if field != "closedVolume":
                            print(
                                f"    {field} (escalado): "
                                f"{_scaled_money(raw, digits)}"
                            )
                        else:
                            print(f"    closedVolume (unidades): {raw / 100:.2f}")

        if event.HasField("errorCode"):
            print(f"  errorCode: {event.errorCode}")

        print()

    async def listen(self):
        while self._running:
            try:
                data = await protocol.read_message(self.reader)
                envelope = protocol.unwrap(data)
                await self._dispatch(envelope)
            except asyncio.IncompleteReadError:
                if self._running:
                    print("✗ Conexión cerrada por el servidor")
                self._running = False

    async def disconnect(self):
        self._running = False
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
            self.writer = None
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
