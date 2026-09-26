import os
import time
import requests

RSI_PERIOD = 14
RSI_LIMIT = 30.0
TIMEOUT = 20

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def get_json(url, params=None, retries=3):
    for attempt in range(retries):
        try:
            response = requests.get(
                url,
                params=params,
                timeout=TIMEOUT
            )
            response.raise_for_status()
            return response.json()

        except requests.RequestException as error:
            print(f"Erro ao acessar {url}: {error}")

            if attempt < retries - 1:
                time.sleep(2)

    return None


def calculate_rsi_wilder(closes, period=14):
    """
    RSI usando o metodo de Wilder (RMA).
    Usa todo o historico recebido para estabilizar o calculo.
    """

    if len(closes) < period + 1:
        return None

    changes = [
        closes[i] - closes[i - 1]
        for i in range(1, len(closes))
    ]

    gains = [
        change if change > 0 else 0.0
        for change in changes
    ]

    losses = [
        abs(change) if change < 0 else 0.0
        for change in changes
    ]

    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period

    for i in range(period, len(changes)):
        average_gain = (
            (average_gain * (period - 1)) + gains[i]
        ) / period

        average_loss = (
            (average_loss * (period - 1)) + losses[i]
        ) / period

    if average_loss == 0:
        if average_gain == 0:
            return 50.0
        return 100.0

    rs = average_gain / average_loss

    rsi = 100 - (100 / (1 + rs))

    return rsi


def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN nao configurado.")
        return

    if not TELEGRAM_CHAT_ID:
        print("TELEGRAM_CHAT_ID nao configurado.")
        return

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    try:
        response = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message
            },
            timeout=TIMEOUT
        )

        response.raise_for_status()

        print("Mensagem enviada ao Telegram.")

    except requests.RequestException as error:
        print(f"Erro ao enviar Telegram: {error}")


# ==========================================================
# BINANCE FUTURES USD-M
# ==========================================================

def get_binance_symbols():
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"

    data = get_json(url)

    if not data:
        return []

    symbols = []

    for item in data.get("symbols", []):
        if (
            item.get("quoteAsset") == "USDT"
            and item.get("contractType") == "PERPETUAL"
            and item.get("status") == "TRADING"
        ):
            symbols.append(item["symbol"])

    return symbols


def get_binance_closes(symbol):
    url = "https://fapi.binance.com/fapi/v1/klines"

    data = get_json(
        url,
        params={
            "symbol": symbol,
            "interval": "4h",
            "limit": 200
        }
    )

    if not data:
        return []

    now_ms = int(time.time() * 1000)

    closed_candles = [
        candle
        for candle in data
        if int(candle[6]) < now_ms
    ]

    closes = [
        float(candle[4])
        for candle in closed_candles
    ]

    return closes


def scan_binance():
    print("Iniciando Binance Futures USD-M...")

    results = []

    symbols = get_binance_symbols()

    print(
        f"Binance: {len(symbols)} contratos "
        f"perpetuos USDT encontrados."
    )

    for number, symbol in enumerate(symbols, start=1):

        closes = get_binance_closes(symbol)

        rsi = calculate_rsi_wilder(
            closes,
            RSI_PERIOD
        )

        if rsi is not None and rsi <= RSI_LIMIT:
            results.append(
                (symbol, rsi)
            )

        if number % 50 == 0:
            print(
                f"Binance: "
                f"{number}/{len(symbols)} analisados."
            )

        time.sleep(0.03)

    return results


# ==========================================================
# OKX USDT-M PERPETUAL SWAPS
# ==========================================================

def get_okx_symbols():
    url = "https://www.okx.com/api/v5/public/instruments"

    data = get_json(
        url,
        params={
            "instType": "SWAP"
        }
    )

    if not data:
        return []

    if data.get("code") != "0":
        print(
            "Erro retornado pela OKX:",
            data
        )
        return []

    symbols = []

    for item in data.get("data", []):

        instrument_id = item.get("instId", "")

        if (
            item.get("settleCcy") == "USDT"
            and item.get("state") == "live"
            and instrument_id.endswith("-USDT-SWAP")
        ):
            symbols.append(instrument_id)

    return symbols


def get_okx_closes(symbol):
    url = "https://www.okx.com/api/v5/market/history-candles"

    data = get_json(
        url,
        params={
            "instId": symbol,
            "bar": "4H",
            "limit": 200
        }
    )

    if not data:
        return []

    if data.get("code") != "0":
        return []

    candles = data.get("data", [])

    closed_candles = [
        candle
        for candle in candles
        if len(candle) > 8
        and candle[8] == "1"
    ]

    # OKX retorna do candle mais novo para o mais antigo.
    # Para calcular o RSI precisamos da ordem cronologica.
    closed_candles.reverse()

    closes = [
        float(candle[4])
        for candle in closed_candles
    ]

    return closes


def scan_okx():
    print("Iniciando OKX USDT-M Perpetual...")

    results = []

    symbols = get_okx_symbols()

    print(
        f"OKX: {len(symbols)} contratos "
        f"perpetuos USDT encontrados."
    )

    for number, symbol in enumerate(symbols, start=1):

        closes = get_okx_closes(symbol)

        rsi = calculate_rsi_wilder(
            closes,
            RSI_PERIOD
        )

        if rsi is not None and rsi <= RSI_LIMIT:
            results.append(
                (symbol, rsi)
            )

        if number % 50 == 0:
            print(
                f"OKX: "
                f"{number}/{len(symbols)} analisados."
            )

        time.sleep(0.05)

    return results


def format_results(exchange, results):
    results.sort(
        key=lambda item: item[1]
    )

    lines = [
        f"{exchange} - RSI 4H <= {RSI_LIMIT:.0f}"
    ]

    for symbol, rsi in results:
        lines.append(
            f"{symbol}: RSI {rsi:.2f}"
        )

    return "\n".join(lines)


def main():
    print("======================================")
    print("Scanner RSI Futures iniciado.")
    print("Timeframe: 4H")
    print("RSI: Wilder 14")
    print("Limite: RSI <= 30")
    print("Somente candles fechados.")
    print("======================================")

    binance_results = scan_binance()

    okx_results = scan_okx()

    messages = []

    if binance_results:
        messages.append(
            format_results(
                "BINANCE FUTURES",
                binance_results
            )
        )

    if okx_results:
        messages.append(
            format_results(
                "OKX PERPETUAL",
                okx_results
            )
        )

    if messages:

        message = (
            "ALERTA RSI 4H\n\n"
            + "\n\n".join(messages)
            + "\n\n"
            + "RSI 14 (Wilder/RMA)\n"
            + "Candle 4H fechado"
        )

        send_telegram(message)

    else:
        print(
            "Nenhum contrato com RSI <= 30 "
            "nesta execucao."
        )

    if binance_failed:\n        print("Scanner finalizado com falha na Binance.")\n        raise SystemExit(1)\n\n    print("Scanner finalizado.")


if __name__ == "__main__":
    main()
