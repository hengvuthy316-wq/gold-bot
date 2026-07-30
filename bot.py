import os
import logging
import yfinance as yf
from google import genai
from google.genai import types
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# ------------------------------------------------------------------------------
# 📊 TECHNICAL INDICATOR CALCULATORS & CONVERTER
# ------------------------------------------------------------------------------

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_pro_gold_data():
    try:
        gold = yf.Ticker("GC=F") # Gold Futures (XAU/USD)
        hist = gold.history(period="10d", interval="1h")
        
        if hist.empty:
            return None

        current_price = hist['Close'].iloc[-1]
        prev_price = hist['Close'].iloc[-24] if len(hist) >= 24 else hist['Close'].iloc[0]
        change = current_price - prev_price
        change_pct = (change / prev_price) * 100
        
        high_24h = hist['High'].tail(24).max()
        low_24h = hist['Low'].tail(24).min()

        # Indicators
        hist['EMA20'] = hist['Close'].ewm(span=20, adjust=False).mean()
        hist['EMA50'] = hist['Close'].ewm(span=50, adjust=False).mean()
        hist['RSI'] = calculate_rsi(hist['Close'], 14)

        ema20 = round(hist['EMA20'].iloc[-1], 2)
        ema50 = round(hist['EMA50'].iloc[-1], 2)
        rsi = round(hist['RSI'].iloc[-1], 2)

        # Cambodian Gold Price Conversion
        # 1 Oz = 31.1034768 grams, 1 Damlung (តម្លឹង) = 37.5 grams, 1 Chi (ជី) = 3.75 grams
        price_per_gram = current_price / 31.1034768
        price_damlung = round(price_per_gram * 37.5, 2)
        price_chi = round(price_damlung / 10, 2)

        return {
            "price": round(current_price, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "high": round(high_24h, 2),
            "low": round(low_24h, 2),
            "ema20": ema20,
            "ema50": ema50,
            "rsi": rsi,
            "price_damlung": price_damlung,
            "price_chi": price_chi,
            "raw_history": hist[['Close', 'EMA20', 'EMA50', 'RSI']].tail(10).to_string()
        }
    except Exception as e:
        logging.error(f"Error fetching pro gold data: {e}")
        return None

# ------------------------------------------------------------------------------
# 🤖 BOT COMMANDS
# ------------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_markdown(
        "👋 **សួស្តី! ខ្ញុំជា Pro Trader Gold Analysis Bot!** 🪙📈\n\n"
        "🛠 **Commands ប្រើប្រាស់៖**\n"
        "• `/gold` — មើលតម្លៃមាស XAU/USD & តម្លៃមាសស្រុកខ្មែរ (តម្លឹង/ជី)\n"
        "• `/trader` ឬ `/analyze` — វិភាគបច្ចេកទេស Pro Trader (EMA, RSI, Entry, TP/SL)\n"
    )

# 1. Command /gold ( Real-time Price + Cambodian Conversion )
async def cmd_gold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(action="typing")
    data = get_pro_gold_data()
    
    if not data:
        await update.message.reply_text("❌ មិនអាចទាញទិន្នន័យទីផ្សារមាសបានទេនៅពេលនេះ!")
        return

    status_icon = "🟢 +" if data['change'] >= 0 else "🔴 "
    
    msg = (
        "🪙 **របាយការណ៍តម្លៃមាស (XAU/USD & ស្រុកខ្មែរ)**\n"
        "-----------------------------------\n"
        f"💵 **XAU/USD Spot:** `${data['price']}` / oz\n"
        f"📊 **ការប្រែប្រួល 24h:** {status_icon}${data['change']} ({data['change_pct']}%)\n"
        f"📈 **High (24h):** `${data['high']}` | 📉 **Low (24h):** `${data['low']}`\n"
        "-----------------------------------\n"
        "🇰🇭 **ប្រៀបធៀបតម្លៃមាសស្រុកខ្មែរ (ប៉ាន់ស្មាន)៖**\n"
        f"🥇 **១ តម្លឹង:** `${data['price_damlung']}`\n"
        f"🥈 **១ ជី:** `${data['price_chi']}`\n"
        "-----------------------------------\n"
        "💡 វាយ `/trader` សម្រាប់សញ្ញា Trader (RSI, EMA, TP/SL)!"
    )
    await update.message.reply_markdown(msg)

# 2. Command /trader or /analyze ( Pro Trader Analysis )
async def cmd_trader(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(action="typing")
    data = get_pro_gold_data()
    
    if not data or not ai_client:
        await update.message.reply_text("❌ មិនអាចទាញទិន្នន័យ ឬ AI មិនទាន់ ready ទេ។")
        return

    rsi_status = "Overbought 🔴 (ប្រយ័ត្នបកក្រោយ)" if data['rsi'] > 70 else "Oversold 🟢 (តំបន់ទិញ)" if data['rsi'] < 30 else "Neutral 🟡 (ធម្មតា)"

    prompt = f"""
    អ្នកគឺជា Pro Gold Trader & Technical Analyst។ ធ្វើការវិភាគទីផ្សារមាស (XAU/USD) ផ្អែកលើ Indicators ខាងក្រោម៖
    - តម្លៃបច្ចុប្បន្ន: ${data['price']} (24h High: ${data['high']}, Low: ${data['low']})
    - EMA 20: ${data['ema20']} | EMA 50: ${data['ema50']}
    - RSI (14): {data['rsi']} ({rsi_status})
    - ប្រវត្តិទិន្នន័យចុងក្រោយ:
    {data['raw_history']}

    សូមសរសេររបាយការណ៍វិភាគសម្រាប់ Trader ជាភាសាខ្មែរ តាមទម្រង់ច្បាស់លាស់ខាងក្រោម៖

    📈 **១. ទិសដៅទីផ្សារ (Market Trend):** (Bullish / Bearish / Sideways)
    📊 **២. សញ្ញា Indicators (Technical Breakdown):**
       - RSI Condition
       - EMA Cross/Trend
    🛡 **៣. តំបន់សំខាន់ៗ (Key Levels):**
       - Resistance (R1, R2)
       - Support (S1, S2)
    🎯 **៤. យុទ្ធសាស្ត្រ Trade (Trading Setup):**
       - ជម្រើស: (BUY / SELL / WAIT)
       - Entry Zone: $...
       - Take Profit (TP): $...
       - Stop Loss (SL): $...
    ⚠️ **៥. ការគ្រប់គ្រងហានិភ័យ (Risk Management Advice):**
    """

    try:
        system_instruction = "អ្នកគឺជា Pro Trader ជំនាញវិភាគមាស XAU/USD។ សរសេររបាយការណ៍វិភាគបច្ចេកទេសខ្លី ខ្លឹម ត្រឹមត្រូវ និងច្បាស់លាស់បំផុតសម្រាប់ Trader។"
        
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system_instruction)
        )
        await update.message.reply_text(response.text)
    except Exception as e:
        logging.error(f"Trader Analysis Error: {e}")
        await update.message.reply_text("❌ មានបញ្ហាក្នុងការវិភាគ Pro Trader!")

def main():
    print("🤖 Starting Pro Trader Gold Bot...")
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("gold", cmd_gold))
    app.add_handler(CommandHandler("price", cmd_gold))
    app.add_handler(CommandHandler("trader", cmd_trader))
    app.add_handler(CommandHandler("analyze", cmd_trader))

    print("✅ Pro Trader Gold Bot is running...")
    app.run_polling(poll_interval=1.0)

if __name__ == "__main__":
    main()
