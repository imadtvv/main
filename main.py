import subprocess, random, string, threading, os, time, requests, socket
from flask import Flask
from threading import Thread
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# ==========================================
# 1. CONFIG & DATABASE
# ==========================================
TOKEN = "8758053991:AAGZWYeE93DDB7PKxyiGksik2KBe81ONIb4"
ADMIN_ID = 5317640929

db = {
    "users": {}, 
    "nodes": [], # كيتزادوا من الأدمن: [{"name": "", "ip": "", "port": 443, "badge": "", "price": 0, "type": "Free", "speed": "1Gbps"}]
    "codes": {}, 
    "used_codes": {}, 
    "active_lives": {},
    "bot_status": True
}

# ==========================================
# 2. NODE MONITORING (محرك فحص اتصال السيرفرات)
# ==========================================
def check_node_status(ip, port=443):
    """دالة كتشوف واش السيرفر خدام ولا لا عبر فحص المنفذ"""
    try:
        # كيحاول يفتح اتصال بسيط فـ 2 ثواني
        with socket.create_connection((ip, port), timeout=2):
            return "🟢 متصل"
    except:
        return "🔴 غير متصل"

# ==========================================
# 3. FLASK & UPTIME
# ==========================================
app_flask = Flask('')
@app_flask.route('/')
def home(): return "🟢 NOVA V6 MONITORING IS ACTIVE"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)

# ==========================================
# 4. CORE ENGINES
# ==========================================
def get_user(user_id, name="User"):
    if user_id not in db["users"]:
        db["users"][user_id] = {
            "name": name, "points": 0, "badge": "👤 مبتدئ", 
            "solo_slots": 0, "group_slots": 0, "is_vip": False, "is_banned": False, "lives_count": 0
        }
    return db["users"][user_id]

def generate_random_code():
    return "NOVA-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# ==========================================
# 5. UI GENERATORS
# ==========================================
def main_menu(user_id):
    u = get_user(user_id)
    admin_icon = "👑 الإمبراطور" if user_id == ADMIN_ID else u['badge']
    txt = (f"💎 **NOVA TV V6 MAX**\n━━━━━━━━━━━━━━\n"
           f"🏅 اللقب: {admin_icon}\n💰 الرصيد: {u['points']} نقطة\n"
           f"⚡ Solo: {u['solo_slots']} | 👥 Group: {u['group_slots']}\n📺 بثوثك: {u['lives_count']}")
    
    kb = [
        [InlineKeyboardButton("⚡ SOLO LIVE", callback_data="mode_solo"), InlineKeyboardButton("👥 GROUP LIVE", callback_data="mode_group")],
        [InlineKeyboardButton("🛒 المتجر", callback_data="store"), InlineKeyboardButton("🎫 تفعيل كود", callback_data="redeem_code")],
        [InlineKeyboardButton("📊 حالة السيرفرات", callback_data="node_status_check")]
    ]
    if user_id == ADMIN_ID: kb.append([InlineKeyboardButton("👑 لوحة التحكم", callback_data="admin_main")])
    return txt, InlineKeyboardMarkup(kb)

# ==========================================
# 6. CALLBACK HANDLERS
# ==========================================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    u = get_user(user_id)
    data = query.data
    await query.answer()

    if data == "node_status_check":
        if not db["nodes"]:
            await query.edit_message_text("❌ لا توجد سيرفرات مضافة حالياً.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="back")]]))
            return
        txt = "📊 **حالة السيرفرات الحالية:**\n\n"
        for n in db["nodes"]:
            status = check_node_status(n['ip'], n.get('port', 443))
            txt += f"🖥️ {n['name']} -> {status}\n🚀 السرعة: {n['speed']}\n━━━━━━━━━━━━━━\n"
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="back")]]))

    elif data.startswith("mode_"):
        mode = data.split("_")[1]
        if (mode == "solo" and u["solo_slots"] < 1) or (mode == "group" and u["group_slots"] < 1):
            await query.edit_message_text("❌ ليس لديك مقاعد كافية!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="back")]]))
            return
        
        context.user_data.update({"mode": mode, "step": "sel_node"})
        btns = []
        for i, n in enumerate(db["nodes"]):
            status = check_node_status(n['ip'], n.get('port', 443))
            btns.append([InlineKeyboardButton(f"{status} | {n['name']} ({n['speed']})", callback_data=f"node_{i}")])
        btns.append([InlineKeyboardButton("⬅️ إلغاء", callback_data="back")])
        await query.edit_message_text("🌐 اختر السيرفر المناسب (تأكد أنه متصل 🟢):", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("node_"):
        idx = int(data.split("_")[1])
        node = db["nodes"][idx]
        if check_node_status(node['ip'], node.get('port', 443)) == "🔴 غير متصل":
            await query.answer("❌ هاد السيرفر طافي حالياً، اختار واحد آخر.", show_alert=True)
            return
        context.user_data.update({"node_name": node["name"], "node_badge": node["badge"]})
        max_s = 1 if context.user_data["mode"] == "solo" else 5
        context.user_data.update({"total": max_s, "current": 1, "list": [], "step": "get_name"})
        await query.edit_message_text(f"📝 دخل سمية البث (1/{max_s}):")

    elif data == "admin_main" and user_id == ADMIN_ID:
        kb = [[InlineKeyboardButton("➕ إضافة Node (IP)", callback_data="adm_add_node")],
              [InlineKeyboardButton("🎫 توليد كود آلي", callback_data="adm_create_code")],
              [InlineKeyboardButton("📣 إعلان عام", callback_data="adm_broadcast")],
              [InlineKeyboardButton("⚙️ حالة البوت", callback_data="adm_toggle_bot")],
              [InlineKeyboardButton("⬅️ رجوع", callback_data="back")]]
        await query.edit_message_text("👑 **لوحة التحكم العليا**", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "adm_add_node" and user_id == ADMIN_ID:
        context.user_data["step"] = "wait_node_data"
        await query.edit_message_text("صيفط معلومات السيرفر هكا:\n`الاسم | IP | Port | اللقب | السعر | النوع | السرعة`\n\nمثال:\n`فرنسا 1 | 152.10.1.5 | 443 | 🗼 باريس | 100 | VIP | 2Gbps`")

    elif data == "back":
        txt, kb = main_menu(user_id)
        await query.edit_message_text(txt, reply_markup=kb, parse_mode="Markdown")

# ==========================================
# 7. TEXT & ADMIN HANDLERS
# ==========================================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u = get_user(user_id)
    text = update.message.text
    step = context.user_data.get("step")

    if step == "wait_node_data" and user_id == ADMIN_ID:
        try:
            p = [i.strip() for i in text.split("|")]
            db["nodes"].append({"name":p[0], "ip":p[1], "port":int(p[2]), "badge":p[3], "price":int(p[4]), "type":p[5], "speed":p[6]})
            await update.message.reply_text(f"✅ تم إضافة {p[0]} بنجاح!")
        except: await update.message.reply_text("❌ خطأ في الصيغة!")
        context.user_data.clear()

    elif step == "get_name":
        context.user_data.update({"temp_n": text, "step": "get_key"})
        await update.message.reply_text("🔑 Stream Key:")
    elif step == "get_key":
        context.user_data.update({"temp_k": text, "step": "get_link"})
        await update.message.reply_text("🔗 M3U8 Link:")
    elif step == "get_link":
        context.user_data["list"].append({"n": context.user_data["temp_n"], "k": context.user_data["temp_k"], "l": text})
        if context.user_data["current"] < context.user_data["total"]:
            context.user_data["current"] += 1 ; context.user_data["step"] = "get_name"
            await update.message.reply_text(f"📝 سمية البث ({context.user_data['current']}/{context.user_data['total']}):")
        else:
            await update.message.reply_text("🚀 جاري إطلاق البثوث...")
            for item in context.user_data["list"]:
                target = f"rtmps://live-api-s.facebook.com:443/rtmp/{item['k']}"
                subprocess.Popen(['ffmpeg', '-re', '-i', item['l'], '-c', 'copy', '-f', 'flv', target])
            u["badge"] = context.user_data["node_badge"]
            if context.user_data["mode"] == "solo": u["solo_slots"] -= 1
            else: u["group_slots"] -= 1
            await update.message.reply_text("✅ تم الإطلاق بنجاح!", reply_markup=main_menu(user_id)[1])
            context.user_data.clear()

# ==========================================
# 8. START & RUN
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt, kb = main_menu(update.effective_user.id)
    await update.message.reply_text(txt, reply_markup=kb, parse_mode="Markdown")

if __name__ == "__main__":
    Thread(target=run_flask).start()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("🌟 NOVA V6 MAX MONITORING STARTED")
    app.run_polling()
