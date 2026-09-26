import os
import time
import requests

RSI_PERIOD = 14
RSI_LIMIT = 30.0
TIMEOUT = 15

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def get_json(url, params=None, retries=3):
    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, timeout=TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            if attempt == retries - 1:
                print(f"Erro ao acessar {url}: {e}")
                return None
            time.sleep(2)


def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None

    closes = closes[-(period + 1):]

    gains = []
    losses = []

    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]

        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    average_gain = sum(gains) / period
    average_loss = sum(losses) / period

    if average_loss == 0:
        return 100.0

    rs = average_gain / average_loss
    return 100 - (100 / (1 + rs))


def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram ainda não configurado.")
        print(message)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

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
    except requests.RequestException as e:
        print(f"Erro ao enviar Telegram: {e}")


def get_binance_symbols():
    data = get_json("https://api.binance.com/api/v3/exchangeInfo")

    if not data:
        return []

    symbols = []

    for item in data.get("symbols", []):
        if (
            item.get("quoteAsset") == "USDT"
            and item.get("status") == "TRADING"
            and item.get("isSpotTradingAllowed", True)
        ):
            symbols.append(item["symbol"])

    return symbols


def get_binance_closes(symbol):
    data = get_json(
        "https://api.binance.com/api/v3/klines",
        params={
            "symbol": symbol,
            "interval": "4h",
            "limit": 20
        }
    )

    if not data:
        return []

    now_ms = int(time.time() * 1000)

    closed_candles = [
        candle for candle in data
        if int(candle[6]) < now_ms
    ]

    return [float(candle[4]) for candle in closed_candles]


def scan_binance():
    print("Iniciando Binance...")

    results = []
    symbols = get_binance_symbols()

    print(f"Binance: {len(symbols)} pares USDT encontrados.")

    for number, symbol in enumerate(symbols, start=1):
        closes = get_binance_closes(symbol)
        rsi = calculate_rsi(closes, RSI_PERIOD)

        if rsi is not None and rsi <= RSI_LIMIT:
            results.append((symbol, rsi))

        if number % 50 == 0:
            print(f"Binance: {number}/{len(symbols)} analisados.")

        time.sleep(0.05)

    return results


def get_okx_symbols():
    data = get_json(
        "https://www.okx.com/api/v5/public/instruments",
        params={"instType": "SPOT"}
    )

    if not data or data.get("code") != "0":
        return []

    symbols = []

    for item in data.get("data", []):
        if (
            item.get("quoteCcy") == "USDT"
            and item.get("state") == "live"
        ):
            symbols.append(item["instId"])

    return symbols


def get_okx_closes(symbol):
    data = get_json(
        "https://www.okx.com/api/v5/market/candles",
        params={
            "instId": symbol,
            "bar": "4H",
            "limit": 20
        }
    )

    if not data or data.get("code") != "0":
        return []

    candles = data.get("data", [])

    # Na OKX, confirm == "1" significa candle concluído.
    closed_candles = [
        candle for candle in candles
        if len(candle) > 8 and candle[8] == "1"
    ]

    # A OKX devolve os candles do mais recente para o mais antigo.
    closed_candles.reverse()

    return [float(candle[4]) for candle in closed_candles]


def scan_okx():
    print("Iniciando OKX...")

    results = []
    symbols = get_okx_symbols()

    print(f"OKX: {len(symbols)} pares USDT encontrados.")

    for number, symbol in enumerate(symbols, start=1):
        closes = get_okx_closes(symbol)
        rsi = calculate_rsi(closes, RSI_PERIOD)

        if rsi is not None and rsi <= RSI_LIMIT:
            results.append((symbol, rsi))

        if number % 50 == 0:
            print(f"OKX: {number}/{len(symbols)} analisados.")

        # Pequena pausa para respeitar os limites da API.
        time.sleep(0.06)

    return results


def format_results(exchange, results):
    if not results:
        return f"{exchange}: nenhum par com RSI <= {RSI_LIMIT:.0f}."

    results.sort(key=lambda x: x[1])

    lines = [f"{exchange} - RSI 4H <= {RSI_LIMIT:.0f}"]

    for symbol, rsi in results:
        lines.append(f"{symbol}: RSI {rsi:.2f}")

    return "\n".join(lines)


def main():
    print("Scanner RSI iniciado.")

    binance_results = scan_binance()
    okx_results = scan_okx()

    messages = []

    if binance_results:
        messages.append(format_results("BINANCE", binance_results))

    if okx_results:
        messages.append(format_results("OKX", okx_results))

    if messages:
        message = (
            "ALERTA RSI 4H\n\n"
            + "\n\n".join(messages)
            + "\n\nRSI calculado com candle 4H fechado."
        )
        send_telegram(message)
    else:
        print("Nenhum RSI <= 30 encontrado nesta execução.")

    print("Scanner finalizado.")


if __name__ == "__main__":
    main()
