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
# 📊 FUNCTION GET GOLD DATA (XAU/USD)
# ------------------------------------------------------------------------------
def get_gold_data():
    try:
        gold = yf.Ticker("GC=F") # Gold Futures (XAU/USD)
        hist = gold.history(period="5d", interval="1h")
        
        if hist.empty:
            return None

        current_price = hist['Close'].iloc[-1]
        prev_price = hist['Close'].iloc[-24] if len(hist) >= 24 else hist['Close'].iloc[0]
        change = current_price - prev_price
        change_pct = (change / prev_price) * 100
        
        high_24h = hist['High'].tail(24).max()
        low_24h = hist['Low'].tail(24).min()

        return {
            "price": round(current_price, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "high": round(high_24h, 2),
            "low": round(low_24h, 2),
            "raw_history": hist.tail(10).to_string()
        }
    except Exception as e:
        logging.error(f"Error fetching gold data: {e}")
        return None

# ------------------------------------------------------------------------------
# 🤖 BOT COMMANDS
# ------------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_markdown(
        "👋 **សួស្តី! ខ្ញុំជា XAU/USD Gold Market Analysis Bot!** 🪙📈\n\n"
        "🛠 **Commands ប្រើប្រាស់៖**\n"
        "• `/gold` — មើលតម្លៃមាស Real-time បច្ចុប្បន្ន\n"
        "• `/analyze` — ឱ្យ AI វិភាគបច្ចេកទេសទីផ្សារមាស (Trend, Support/Resistance, Strategy)\n"
    )

# 1. Command /gold ( realtime price )
async def cmd_gold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(action="typing")
    data = get_gold_data()
    
    if not data:
        await update.message.reply_text("❌ មិនអាចទាញទិន្នន័យទីផ្សារមាសបានទេនៅពេលនេះ!")
        return

    status_icon = "🟢 +" if data['change'] >= 0 else "🔴 "
    
    msg = (
        "🪙 **របាយការណ៍តម្លៃមាស (XAU/USD)**\n"
        "-----------------------------------\n"
        f"💵 **តម្លៃបច្ចុប្បន្ន:** `${data['price']}` / oz\n"
        f"📊 **ការប្រែប្រួល 24h:** {status_icon}${data['change']} ({data['change_pct']}%)\n"
        f"📈 **តម្លៃខ្ពស់បំផុត (24h):** `${data['high']}`\n"
        f"📉 **តម្លៃទាបបំផុត (24h):** `${data['low']}`\n"
        "-----------------------------------\n"
        "💡 វាយ `/analyze` ដើម្បីឱ្យ AI ធ្វើការវិភាគបច្ចេកទេសទីផ្សារ!"
    )
    await update.message.reply_markdown(msg)

# 2. Command /analyze ( AI Technical Analysis )
async def cmd_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(action="typing")
    data = get_gold_data()
    
    if not data or not ai_client:
        await update.message.reply_text("❌ មិនអាចទាញទិន្នន័យ ឬ AI មិនទាន់ ready ទេ។")
        return

    prompt = f"""
    វិភាគទីផ្សារមាស (XAU/USD) ផ្អែកលើទិន្នន័យបច្ចេកទេសខាងក្រោម៖
    - តម្លៃបច្ចុប្បន្ន: ${data['price']}
    - ការប្រែប្រួល 24h: {data['change']} ({data['change_pct']}%)
    - ខ្ពស់បំផុត 24h: ${data['high']}
    - ទាបបំផុត 24h: ${data['low']}
    - ប្រវត្តិ 10h ចុងក្រោយ:
    {data['raw_history']}

    សូមធ្វើការវិភាគ និងសរសេររបាយការណ៍ជាភាសាខ្មែរ តាមទម្រង់ខាងក្រោម៖
    1. 📈 **ទិសដៅទីផ្សារ (Market Trend):** (Bullish / Bearish / Neutral)
    2. 🛡 **តំបន់គាំទ្រ និងទប់ (Support & Resistance Levels):**
    3. 💡 **ការវិភាគបច្ចេកទេស និងយុទ្ធសាស្ត្រ (Technical & Trading Strategy):**
    4. ⚠️ **ការព្រមានហានិភ័យ (Risk Management):**
    """

    try:
        system_instruction = "អ្នកគឺជាអ្នកជំនាញវិភាគទីផ្សារហិរញ្ញវត្ថុ និងមាស (Financial & Gold Market Analyst)។ សរសេររបាយការណ៍ជាភាសាខ្មែរ ច្បាស់លាស់ វិជ្ជាជីវៈ និងងាយយល់។"
        
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system_instruction)
        )
        await update.message.reply_text(response.text)
    except Exception as e:
        logging.error(f"Analysis Error: {e}")
        await update.message.reply_text("❌ មានបញ្ហាក្នុងការវិភាគ AI!")

def main():
    print("🤖 Starting Gold Analysis Bot...")
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("gold", cmd_gold))
    app.add_handler(CommandHandler("price", cmd_gold))
    app.add_handler(CommandHandler("analyze", cmd_analyze))

    print("✅ Gold Bot is running...")
    app.run_polling(poll_interval=1.0)

if __name__ == "__main__":
    main()
