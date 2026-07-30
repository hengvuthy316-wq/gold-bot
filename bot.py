import os
import logging
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import httpx
import yfinance as yf
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

# ------------------------------------------------------------------------------
# 🌐 DUMMY DOCKER/RENDER HEALTH CHECK HTTP SERVER
# ------------------------------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK - Bot is running")

def start_health_check_server():
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    logging.info(f"🌐 Health check HTTP server listening on port {port}")
    server.serve_forever()

# Start HTTP server in a background daemon thread for Render port scanning
threading.Thread(target=start_health_check_server, daemon=True).start()

# ------------------------------------------------------------------------------
# 🔑 CONFIGURATION (CODEX / 9ROUTER API & TELEGRAM)
# ------------------------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CODEX_API_KEY = os.environ.get("CODEX_API_KEY", "sk_9router_default")
CODEX_BASE_URL = os.environ.get("CODEX_BASE_URL", "https://9router-production-4db4.up.railway.app/v1")
CODEX_MODEL = os.environ.get("CODEX_MODEL", "cx/gpt-5.6-terra")

# ------------------------------------------------------------------------------
# 📊 TECHNICAL INDICATOR CALCULATOR (MULTI-TIMEFRAME)
# ------------------------------------------------------------------------------

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_gold_data_by_timeframe(interval="15m", period="5d"):
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
            "raw_history": hist[['Open', 'High', 'Low', 'Close', 'EMA20', 'EMA50', 'RSI']].tail(12).to_string()
        }
    except Exception as e:
        logging.error(f"Error fetching data for {interval}: {e}")
        return None

# ------------------------------------------------------------------------------
# 🧠 CODEX / 9ROUTER AI CALLER (OPENAI-COMPATIBLE)
# ------------------------------------------------------------------------------
async def ask_codex_ai(prompt: str, system_instruction: str) -> str:
    """Calls Codex cx/gpt-5.6-terra via 9Router Railway endpoint"""
    url = f"{CODEX_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {CODEX_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": CODEX_MODEL,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        res_data = response.json()
        return res_data["choices"][0]["message"]["content"]

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
        "⚡ *សួស្តី! ខ្ញុំជា Pro Gold Trading Bot (Powered by Codex cx/gpt-5.6-terra)!* 🪙📈\n\n"
        "សូមជ្រើសរើសប៊ូតុងខាងក្រោមដើម្បីមើលតម្លៃមាស ឬវិភាគទីផ្សារ SMC (Smart Money Concepts):"
    )
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")

# Real-time Price Renderer
async def render_gold_price(send_func):
    data = get_gold_data_by_timeframe("15m", "5d")
    if not data:
        await send_func("❌ មិនអាចទាញទិន្នន័យទីផ្សារមាសបានទេនៅពេលនេះ!")
        return

    status_icon = "🟢 +" if data['change'] >= 0 else "🔴 "
    
    msg = (
        "🪙 *របាយការណ៍តម្លៃមាស (XAU/USD & ស្រុកខ្មែរ)*\n"
        "-----------------------------------\n"
        f"💵 *XAU/USD Spot:* `${data['price']}` / oz\n"
        f"📊 *ការប្រែប្រួល:* {status_icon}${data['change']} ({data['change_pct']}%)\n"
        f"📈 *High (24h):* `${data['high']}` | 📉 *Low (24h):* `${data['low']}`\n"
        "-----------------------------------\n"
        "🇰🇭 *ប្រៀបធៀបតម្លៃមាសស្រុកខ្មែរ (ប៉ាន់ស្មាន)៖*\n"
        f"🥇 *១ តម្លឹង:* `${data['price_damlung']}`\n"
        f"🥈 *១ ជី:* `${data['price_chi']}`\n"
        "-----------------------------------\n"
        "👇 *ជ្រើសរើស Mode វិភាគខាងក្រោម៖*"
    )
    await send_func(msg, reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")

# AI Analysis Renderer
async def render_timeframe_analysis(send_func, interval: str, style_name: str, period: str):
    data = get_gold_data_by_timeframe(interval, period)
    if not data:
        await send_func("❌ មិនអាចទាញទិន្នន័យបានទេ។")
        return

    rsi_status = "Overbought 🔴" if data['rsi'] > 70 else "Oversold 🟢" if data['rsi'] < 30 else "Neutral 🟡"

    prompt = f"""
    អ្នកគឺជា Pro SMC (Smart Money Concepts) & Price Action Gold Trader លើទីផ្សារ XAU/USD (Timeframe: {interval})។
    ទិន្នន័យ Candle & Indicators បច្ចុប្បន្ន៖
    - តម្លៃបច្ចុប្បន្ន: ${data['price']} (High 24h: ${data['high']}, Low 24h: ${data['low']})
    - EMA 20: ${data['ema20']} | EMA 50: ${data['ema50']}
    - RSI (14): {data['rsi']} ({rsi_status})
    - តារាងប្រវត្តិ Candle 12 ចុងក្រោយ ({interval}):
    {data['raw_history']}

    សូមធ្វើការវិភាគ Smart Money Concepts (SMC) & Trading Setup សម្រាប់ {style_name} ជាភាសាខ្មែរ (ប្រើ Markdown ស្អាត):

    ១. 📈 *រចនាសម្ព័ន្ធទីផ្សារ (Market Structure {interval}):* (BULLISH / BEARISH / SIDEWAYS) + (BOS/CHoCH Status)
    ២. 📊 *សញ្ញា Indicators & Momentum:* RSI Condition, EMA Trend Support/Resistance
    ៣. 🛡 *តំបន់ POI (Demand Zone / Supply Zone & Order Block):*
       - Supply / Resistance Zone: $...
       - Demand / Support Zone: $...
    ៤. 🎯 *Trading Setup ({style_name}):*
       - *Next Step:* (WAIT RETEST / BUY ON DEMAND / SELL ON SUPPLY)
       - *Action:* (BUY / SELL / WAIT)
       - *Entry Price:* $...
       - *Take Profit (TP):* $...
       - *Stop Loss (SL):* $...
    ៥. ⚠️ *ការគ្រប់គ្រងហានិភ័យ (Risk & Money Management):*
    """

    system_instruction = f"អ្នកគឺជា Codex Pro Trader (cx/gpt-5.6-terra) ជំនាញ XAU/USD (Timeframe {interval})។ សរសេររបាយការណ៍ជា Telegram Markdown (*bold* មិនប្រើ ** ទេ!) ខ្លី ខ្លឹម ច្បាស់លាស់បំផុត។"

    try:
        ai_reply = await ask_codex_ai(prompt, system_instruction)
        
        header = f"⚡ *[{style_name} - Timeframe {interval}]*\n\n"
        full_text = header + ai_reply
        clean_text = full_text.replace("**", "*")
        
        await send_func(clean_text, reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Codex AI Error: {e}")
        await send_func(f"❌ មានបញ្ហាក្នុងការភ្ជាប់ទៅកាន់ Codex AI (cx/gpt-5.6-terra): {e}")

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
    await query.answer()
    
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
        await query.message.reply_text("🔘 *សេរី Menu សម្រាប់ចុចជ្រើសរើស៖*", reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")

def main():
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    print("🤖 Starting Pro Gold Codex Trading Bot (cx/gpt-5.6-terra)...")
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

    print("✅ Pro Gold Codex Bot is running...")
    app.run_polling(poll_interval=1.0)

if __name__ == "__main__":
    main()
