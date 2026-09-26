import os
import time
import requests

RSI_PERIOD = 14
RSI_LIMIT = 25.0
TIMEFRAME = os.environ.get("SCAN_TIMEFRAME", "1H")
RSI_LIMIT = float(os.environ.get("RSI_LIMIT", "25"))
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


def get_okx_closes(symbol, timeframe):
    url = "https://www.okx.com/api/v5/market/history-candles"

    data = get_json(
        url,
        params={
            "instId": symbol,
            "bar": timeframe,
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


def scan_okx(timeframe, rsi_limit):
    print("Iniciando OKX USDT-M Perpetual...")

    results = []

    symbols = get_okx_symbols()

    print(
        f"OKX: {len(symbols)} contratos "
        f"perpetuos USDT encontrados."
    )

    for number, symbol in enumerate(symbols, start=1):

        closes = get_okx_closes(symbol, timeframe)

        rsi = calculate_rsi_wilder(
            closes,
            RSI_PERIOD
        )

        if rsi is not None and rsi <= rsi_limit:
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


def format_results(exchange, results, timeframe, rsi_limit):
    results.sort(
        key=lambda item: item[1]
    )

    lines = [
        f"{exchange} - RSI {timeframe} <= {rsi_limit:.0f}"
    ]

    for symbol, rsi in results:
        lines.append(
            f"{symbol}: RSI {rsi:.2f}"
        )

    return "\n".join(lines)


def main():
    timeframe = TIMEFRAME
    rsi_limit = RSI_LIMIT

    print("======================================")
    print("Scanner RSI OKX iniciado.")
    print(f"Timeframe: {timeframe}")
    print("RSI: Wilder 14")
    print(f"Limite: RSI <= {rsi_limit:.0f}")
    print("Somente candles fechados.")
    print("======================================")

    okx_results = scan_okx(timeframe, rsi_limit)

    if okx_results:
        message = (
            f"ALERTA RSI {timeframe} - OKX\n\n"
            + format_results("OKX PERPETUAL", okx_results, timeframe, rsi_limit)
            + "\n\nRSI 14 (Wilder/RMA)"
            + f"\nCandle {timeframe} fechado"
        )
        send_telegram(message)
    else:
        print(
            f"Nenhum contrato OKX com RSI <= {rsi_limit:.0f} "
            f"no timeframe {timeframe} nesta execucao."
        )

    print("Scanner finalizado.")


if __name__ == "__main__":
    main()
