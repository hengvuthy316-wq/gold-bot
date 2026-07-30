import os
import logging
import yfinance as yf
from google import genai
from google.genai import types
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# ------------------------------------------------------------------------------
# 📊 TECHNICAL INDICATOR CALCULATOR (MULTI-TIMEFRAME)
# ------------------------------------------------------------------------------

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_gold_data_by_timeframe(interval="1h", period="5d"):
    try:
        gold = yf.Ticker("GC=F") # Gold Futures (XAU/USD)
        hist = gold.history(period=period, interval=interval)
        
        if hist.empty:
            return None

        current_price = hist['Close'].iloc[-1]
        prev_price = hist['Close'].iloc[-2]
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
        price_per_gram = current_price / 31.1034768
        price_damlung = round(price_per_gram * 37.5, 2)
        price_chi = round(price_damlung / 10, 2)

        return {
            "interval": interval,
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
        logging.error(f"Error fetching data for {interval}: {e}")
        return None

# ------------------------------------------------------------------------------
# 🔘 INLINE KEYBOARD MENU HELPER
# ------------------------------------------------------------------------------
def get_main_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("💵 តម្លៃមាស Real-time", callback_data="btn_gold"),
        ],
        [
            InlineKeyboardButton("⚡ Scalping (15m)", callback_data="btn_scalp"),
            InlineKeyboardButton("📊 Day Trade (1h)", callback_data="btn_day"),
        ],
        [
            InlineKeyboardButton("🌊 Swing Trade (4h)", callback_data="btn_swing"),
            InlineKeyboardButton("🔄 Refresh Menu", callback_data="btn_menu"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ------------------------------------------------------------------------------
# 🤖 BOT COMMANDS & CALLBACK HANDLERS
# ------------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 **សួស្តី! ខ្ញុំជា Pro Gold Trading Bot (Multi-Timeframe)!** 🪙📈\n\n"
        "សូមជ្រើសរើសប៊ូតុងខាងក្រោមដើម្បីមើលតម្លៃមាស ឬវិភាគទីផ្សារ៖"
    )
    if update.message:
        await update.message.reply_markdown(welcome_text, reply_markup=get_main_menu_keyboard())

# Real-time Price Renderer
async def render_gold_price(send_func):
    data = get_gold_data_by_timeframe("1h", "5d")
    if not data:
        await send_func("❌ មិនអាចទាញទិន្នន័យទីផ្សារមាសបានទេនៅពេលនេះ!")
        return

    status_icon = "🟢 +" if data['change'] >= 0 else "🔴 "
    
    msg = (
        "🪙 **របាយការណ៍តម្លៃមាស (XAU/USD & ស្រុកខ្មែរ)**\n"
        "-----------------------------------\n"
        f"💵 **XAU/USD Spot:** `${data['price']}` / oz\n"
        f"📊 **ការប្រែប្រួល:** {status_icon}${data['change']} ({data['change_pct']}%)\n"
        f"📈 **High (24h):** `${data['high']}` | 📉 **Low (24h):** `${data['low']}`\n"
        "-----------------------------------\n"
        "🇰🇭 **ប្រៀបធៀបតម្លៃមាសស្រុកខ្មែរ (ប៉ាន់ស្មាន)៖**\n"
        f"🥇 **១ តម្លឹង:** `${data['price_damlung']}`\n"
        f"🥈 **១ ជី:** `${data['price_chi']}`\n"
        "-----------------------------------\n"
        "👇 **ជ្រើសរើស Mode វិភាគខាងក្រោម៖**"
    )
    await send_func(msg, reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")

# AI Analysis Renderer
async def render_timeframe_analysis(send_func, interval: str, style_name: str, period: str):
    data = get_gold_data_by_timeframe(interval, period)
    if not data or not ai_client:
        await send_func("❌ មិនអាចទាញទិន្នន័យ ឬ AI មិនទាន់ ready ទេ។")
        return

    rsi_status = "Overbought 🔴" if data['rsi'] > 70 else "Oversold 🟢" if data['rsi'] < 30 else "Neutral 🟡"

    prompt = f"""
    អ្នកគឺជា Pro Trader ជំនាញវិភាគទីផ្សារមាស (XAU/USD) សម្រាប់ប្រភេទ {style_name} (Timeframe: {interval})។
    ទិន្នន័យបច្ចេកទេសបច្ចុប្បន្ន៖
    - តម្លៃ: ${data['price']} (High: ${data['high']}, Low: ${data['low']})
    - EMA 20: ${data['ema20']} | EMA 50: ${data['ema50']}
    - RSI (14): {data['rsi']} ({rsi_status})
    - ទិន្នន័យប្រវត្តិ {interval}:
    {data['raw_history']}

    សូមធ្វើការវិភាគសម្រាប់ {style_name} ជាភាសាខ្មែរ៖
    1. 📈 **ទិសដៅទីផ្សារ (Trend {interval}):** (Bullish / Bearish / Sideways)
    2. 📊 **ភាគរយសញ្ញា Indicators:** RSI condition, EMA Cross
    3. 🛡 **តំបន់គាំទ្រ & ទប់ (Support/Resistance សម្រាប់ {interval}):**
    4. 🎯 **Trading Setup ({style_name}):**
       - Action: (BUY / SELL / WAIT)
       - Entry Price: $...
       - Take Profit (TP): $...
       - Stop Loss (SL): $...
    ⚠️ **៥. ការគ្រប់គ្រងហានិភ័យ (Risk Management):**
    """

    try:
        system_instruction = f"អ្នកគឺជា Pro Trader ជំនាញ {style_name} លើទីផ្សារមាស XAU/USD (Timeframe {interval})។ សរសេររបាយការណ៍ខ្លី ខ្លឹម ច្បាស់លាស់បំផុត។"
        
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system_instruction)
        )
        await send_func(f"⚡ **[{style_name} MODE - Timeframe {interval}]**\n\n" + response.text, reply_markup=get_main_menu_keyboard())
    except Exception as e:
        logging.error(f"Analysis Error: {e}")
        await send_func("❌ មានបញ្ហាក្នុងការវិភាគ AI!")

# Command Callers
async def cmd_gold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(action="typing")
    await render_gold_price(update.message.reply_text)

async def cmd_scalp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(action="typing")
    await render_timeframe_analysis(update.message.reply_text, "15m", "Scalping Mode (ខ្លីរហ័ស)", "2d")

async def cmd_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(action="typing")
    await render_timeframe_analysis(update.message.reply_text, "1h", "Day Trading Mode (ក្នុងថ្ងៃ)", "5d")

async def cmd_swing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(action="typing")
    await render_timeframe_analysis(update.message.reply_text, "4h", "Swing Trading Mode (២-៣ថ្ងៃ)", "1mo")

# Button Click Handler
async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() # Acknowledge button click
    
    data = query.data

    async def reply_from_button(text, reply_markup=None, parse_mode=None):
        if parse_mode:
            await query.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await query.message.reply_text(text, reply_markup=reply_markup)

    if data == "btn_gold":
        await query.message.chat.send_action(action="typing")
        await render_gold_price(reply_from_button)
    elif data == "btn_scalp":
        await query.message.chat.send_action(action="typing")
        await render_timeframe_analysis(reply_from_button, "15m", "Scalping Mode (ខ្លីរហ័ស)", "2d")
    elif data == "btn_day":
        await query.message.chat.send_action(action="typing")
        await render_timeframe_analysis(reply_from_button, "1h", "Day Trading Mode (ក្នុងថ្ងៃ)", "5d")
    elif data == "btn_swing":
        await query.message.chat.send_action(action="typing")
        await render_timeframe_analysis(reply_from_button, "4h", "Swing Trading Mode (២-៣ថ្ងៃ)", "1mo")
    elif data == "btn_menu":
        await query.message.reply_text("🔘 **សេរី Menu សម្រាប់ចុចជ្រើសរើស៖**", reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")

def main():
    print("🤖 Starting Pro Gold Trading Bot with Interactive Buttons...")
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", start))
    app.add_handler(CommandHandler("gold", cmd_gold))
    app.add_handler(CommandHandler("price", cmd_gold))
    app.add_handler(CommandHandler("scalp", cmd_scalp))
    app.add_handler(CommandHandler("15m", cmd_scalp))
    app.add_handler(CommandHandler("day", cmd_day))
    app.add_handler(CommandHandler("1h", cmd_day))
    app.add_handler(CommandHandler("trader", cmd_day))
    app.add_handler(CommandHandler("analyze", cmd_day))
    app.add_handler(CommandHandler("swing", cmd_swing))
    app.add_handler(CommandHandler("4h", cmd_swing))

    # Button Clicks
    app.add_handler(CallbackQueryHandler(handle_button_click))

    print("✅ Pro Gold Bot with Buttons is running...")
    app.run_polling(poll_interval=1.0)

if __name__ == "__main__":
    main()
