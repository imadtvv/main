import subprocess, random, string, threading, psutil, os, time, json
from flask import Flask
from threading import Thread
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# ==========================================
# 1. CONFIG & DATABASE (قاعدة البيانات والإعدادات)
# ==========================================
TOKEN = "8758053991:AAGZWYeE93DDB7PKxyiGksik2KBe81ONIb4"
ADMIN_ID = 5317640929

db = {
    "users": {}, # {id: {"name": "", "points": 0, "badge": "", "solo_slots": 0, "group_slots": 0, "is_vip": False, "is_banned": False}}
    "nodes": [
        {"name": "🐆 سيرفر الفهد", "config": "vless://...", "badge": "🐆 الفهد الوعر", "price": 100, "type": "VIP", "speed": "2Gbps"},
        {"name": "🇫🇷 سيرفر فرنسا مجاني", "config": "vless://...", "badge": "🗼 باريس", "price": 0, "type": "Free", "speed": "100Mbps"}
    ],
    "codes": {
        "NOVA2026": {"type": "points", "value": 500, "usage": "group"}, # كود نقط جماعي
        "SOLOPASS": {"type": "seat_solo", "value": 1, "usage": "single"}, # كود مقعد سولو
        "GROUPPASS": {"type": "seat_group", "value": 1, "usage": "single"} # كود مقعد جماعي
    },
    "used_codes": {}, # {user_id: ["code1", "code2"]}
    "active_lives": {},
    "bot_status": True
}

# ==========================================
# 2. CORE ENGINES (المحركات)
# ==========================================
def get_user(user_id, name="User"):
    if user_id not in db["users"]:
        db["users"][user_id] = {
            "name": name, "points": 20, "badge": "👤 مبتدئ", 
            "solo_slots": 1, "group_slots": 0, "is_vip": False, "is_banned": False, "lives_count": 0
        }
    if user_id not in db["used_codes"]:
        db["used_codes"][user_id] = []
    return db["users"][user_id]

def start_ffmpeg(key, link, lid, user_id, stream_name, node_name):
    # إعداد البث لفيسبوك RTMPS
    target_url = f"rtmps://live-api-s.facebook.com:443/rtmp/{key}"
    cmd = ['ffmpeg', '-re', '-i', link, '-c', 'copy', '-f', 'flv', target_url]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    db["active_lives"][lid] = {"proc": proc, "user_id": user_id, "name": stream_name, "node": node_name}
    db["users"][user_id]["lives_count"] += 1

# ==========================================
# 3. UI GENERATORS (واجهات المستخدم)
# ==========================================
def main_menu(user_id):
    u = get_user(user_id)
    admin_icon = "👑 الإمبراطور" if user_id == ADMIN_ID else u['badge']
    
    txt = (f"💎 **NOVA TV V6 MAX**\n"
           f"━━━━━━━━━━━━━━\n"
           f"👤 الحساب: {u['name']}\n"
           f"🏅 اللقب: {admin_icon}\n"
           f"💰 الرصيد: {u['points']} نقطة\n"
           f"⚡ مقاعد سولو المتاحة: {u['solo_slots']}\n"
           f"👥 مقاعد جماعية المتاحة: {u['group_slots']}\n"
           f"📺 إجمالي بثوثك: {u['lives_count']}")
    
    kb = [
        [InlineKeyboardButton("⚡ SOLO LIVE (بث فردي)", callback_data="mode_solo")],
        [InlineKeyboardButton("👥 GROUP LIVE (5 بثوث)", callback_data="mode_group")],
        [InlineKeyboardButton("🛒 متجر السيرفرات والألقاب", callback_data="store")],
        [InlineKeyboardButton("🎫 تفعيل كود (نقاط/مقاعد)", callback_data="redeem_code")],
        [InlineKeyboardButton("📊 حالة النظام", callback_data="status")]
    ]
    if user_id == ADMIN_ID:
        kb.append([InlineKeyboardButton("👑 لوحة تحكم الإمبراطور", callback_data="admin_main")])
        
    return txt, InlineKeyboardMarkup(kb)

def admin_menu():
    kb = [
        [InlineKeyboardButton("➕ إضافة Node Vless", callback_data="adm_add_node")],
        [InlineKeyboardButton("🎫 إنشاء كود (نقاط/مقاعد)", callback_data="adm_create_code")],
        [InlineKeyboardButton("📣 إرسال إعلان للجميع", callback_data="adm_broadcast")],
        [InlineKeyboardButton("👥 قائمة المستخدمين", callback_data="adm_users")],
        [InlineKeyboardButton("⚙️ إيقاف/تشغيل البوت", callback_data="adm_toggle_bot")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="back")]
    ]
    return InlineKeyboardMarkup(kb)

# ==========================================
# 4. CALLBACK HANDLERS (معالجة الأزرار)
# ==========================================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    u = get_user(user_id)
    data = query.data
    await query.answer()

    # --- القائمة الرئيسية للمستخدم ---
    if data.startswith("mode_"):
        mode = data.split("_")[1]
        
        # التحقق من المقاعد
        if mode == "solo" and u["solo_slots"] < 1:
            await query.edit_message_text("❌ معندكش مقاعد Solo! اشري مقعد أو دخل كود.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="back")]]))
            return
        if mode == "group" and u["group_slots"] < 1:
            await query.edit_message_text("❌ معندكش مقاعد Group! اشري مقعد أو دخل كود.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="back")]]))
            return

        context.user_data.update({"mode": mode, "step": "sel_node"})
        btns = [[InlineKeyboardButton(f"{n['name']} [{n['speed']}]", callback_data=f"node_{i}")] for i, n in enumerate(db["nodes"])]
        btns.append([InlineKeyboardButton("⬅️ إلغاء", callback_data="back")])
        await query.edit_message_text("🌐 اختر السيرفر (Node) لي غتبث منو:", reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("node_"):
        idx = int(data.split("_")[1])
        node = db["nodes"][idx]
        
        if node["type"] == "VIP" and not u["is_vip"]:
            await query.edit_message_text("❌ هاد السيرفر VIP خاص بالمشتركين. دوز للمتجر!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="back")]]))
            return
            
        context.user_data["node_name"] = node["name"]
        context.user_data["node_badge"] = node["badge"]
        
        mode = context.user_data["mode"]
        max_streams = 1 if mode == "solo" else 5
        context.user_data.update({"total": max_streams, "current": 1, "list": [], "step": "get_name"})
        
        await query.edit_message_text(f"📝 دخل سمية البث رقم (1/{max_streams}):")

    elif data == "store":
        txt = "🛒 **متجر NOVA**\nاشري الألقاب والسيرفرات القوية بنقطك:\n\n"
        btns = []
        for i, n in enumerate(db["nodes"]):
            if n["price"] > 0:
                txt += f"• {n['name']} | اللقب: {n['badge']} | السعر: {n['price']} نقطة\n"
                btns.append([InlineKeyboardButton(f"شراء {n['name']}", callback_data=f"buy_node_{i}")])
        btns.append([InlineKeyboardButton("⬅️ رجوع", callback_data="back")])
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(btns))

    elif data.startswith("buy_node_"):
        idx = int(data.split("_")[2])
        node = db["nodes"][idx]
        if u["points"] >= node["price"]:
            u["points"] -= node["price"]
            u["is_vip"] = True
            u["badge"] = node["badge"]
            await query.edit_message_text(f"✅ مبروك! شريتي {node['name']}. اللقب ديالك ولى [{u['badge']}].", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data="back")]]))
        else:
            await query.edit_message_text("❌ نقطك ماكافياش!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data="back")]]))

    elif data == "redeem_code":
        context.user_data["step"] = "wait_code"
        await query.edit_message_text("⌨️ صيفط الكود لي عندك (نقاط أو مقاعد):")

    # --- لوحة الأدمن ---
    elif data == "admin_main" and user_id == ADMIN_ID:
        await query.edit_message_text("👑 **مرحبا بك يا إمبراطور النظام**", reply_markup=admin_menu())

    elif data == "adm_create_code" and user_id == ADMIN_ID:
        context.user_data["step"] = "adm_code_setup"
        await query.edit_message_text("صيفط معلومات الكود بهاد الشكل:\n`اسم_الكود | النوع | القيمة | الاستخدام`\n\nالأنواع: `points`, `seat_solo`, `seat_group`\nالاستخدام: `single` (لشخص واحد), `group` (للجميع)\n\nمثال: `MYCODE | seat_group | 1 | single`")

    elif data == "adm_broadcast" and user_id == ADMIN_ID:
        context.user_data["step"] = "wait_bc_photo"
        await query.edit_message_text("📸 صيفط الصورة ديال الإعلان (أو صيفط نص نيشان إذا ماكاينش صورة):")

    elif data == "adm_toggle_bot" and user_id == ADMIN_ID:
        db["bot_status"] = not db["bot_status"]
        state = "✅ شغال" if db["bot_status"] else "❌ متوقف (صيانة)"
        await query.edit_message_text(f"حالة البوت دابا: {state}", reply_markup=admin_menu())

    elif data == "back":
        txt, kb = main_menu(user_id)
        await query.edit_message_text(txt, reply_markup=kb, parse_mode="Markdown")

# ==========================================
# 5. TEXT HANDLERS (معالجة الرسائل النصية)
# ==========================================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u = get_user(user_id)
    text = update.message.text
    step = context.user_data.get("step")

    # --- إدخال معلومات البث (سولو أو جماعي) ---
    if step == "get_name":
        context.user_data["temp_name"] = text
        context.user_data["step"] = "get_key"
        await update.message.reply_text("🔑 دخل Stream Key ديال الفيسبوك:")

    elif step == "get_key":
        context.user_data["temp_key"] = text
        context.user_data["step"] = "get_link"
        await update.message.reply_text("🔗 دخل رابط M3U8:")

    elif step == "get_link":
        name = context.user_data["temp_name"]
        key = context.user_data["temp_key"]
        link = text
        node_name = context.user_data["node_name"]
        
        context.user_data["list"].append({"name": name, "key": key, "link": link})
        
        if context.user_data["current"] < context.user_data["total"]:
            context.user_data["current"] += 1
            context.user_data["step"] = "get_name"
            await update.message.reply_text(f"📝 ممتاز! دابا دخل سمية البث رقم ({context.user_data['current']}/{context.user_data['total']}):")
        else:
            mode = context.user_data["mode"]
            # خصم المقعد
            if mode == "solo": u["solo_slots"] -= 1
            else: u["group_slots"] -= 1

            await update.message.reply_text(f"🚀 جاري إطلاق {context.user_data['total']} بثوث دقة وحدة عبر {node_name}...")
            
            for item in context.user_data["list"]:
                lid = ''.join(random.choices(string.ascii_uppercase, k=5))
                start_ffmpeg(item['key'], item['link'], lid, user_id, item['name'], node_name)
            
            # تحديث اللقب
            u["badge"] = context.user_data["node_badge"]
            
            txt, kb = main_menu(user_id)
            await update.message.reply_text("✅ تم إطلاق جميع البثوث بنجاح! وتم تحديث لقبك.", reply_markup=kb, parse_mode="Markdown")
            context.user_data.clear()

    # --- تفعيل الأكواد (للمستخدم) ---
    elif step == "wait_code":
        code = text
        if code in db["codes"]:
            cinfo = db["codes"][code]
            
            # التحقق واش استعملو من قبل
            if code in db["used_codes"][user_id]:
                await update.message.reply_text("❌ فايت ليك استعملتي هاد الكود!")
                return

            # إضافة القيمة
            if cinfo["type"] == "points":
                u["points"] += cinfo["value"]
                msg = f"✅ تزادتك {cinfo['value']} نقطة!"
            elif cinfo["type"] == "seat_solo":
                u["solo_slots"] += cinfo["value"]
                msg = f"✅ تزادك {cinfo['value']} مقعد Solo!"
            elif cinfo["type"] == "seat_group":
                u["group_slots"] += cinfo["value"]
                msg = f"✅ تزادك {cinfo['value']} مقعد Group!"

            # تسجيل الاستخدام أو مسح الكود
            if cinfo["usage"] == "single":
                del db["codes"][code] # كود لشخص واحد يتمسح
            else:
                db["used_codes"][user_id].append(code) # كود جماعي يتسجل باش مايعاودش
                
            txt, kb = main_menu(user_id)
            await update.message.reply_text(msg, reply_markup=kb, parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ كود غالط أو سالت الصلاحية ديالو.")
        context.user_data.clear()

    # --- إنشاء كود (للأدمن) ---
    elif step == "adm_code_setup" and user_id == ADMIN_ID:
        try:
            parts = [p.strip() for p in text.split("|")]
            c_name, c_type, c_val, c_usage = parts[0], parts[1], int(parts[2]), parts[3]
            db["codes"][c_name] = {"type": c_type, "value": c_val, "usage": c_usage}
            await update.message.reply_text(f"✅ تم إنشاء الكود بنجاح!\nالكود: `{c_name}`\nالنوع: {c_type}\nالقيمة: {c_val}\nالاستخدام: {c_usage}", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text("❌ خطأ فالصيغة! تأكد درتي | بين المعلومات.")
        context.user_data.clear()

    # --- إرسال إعلان نصي (للأدمن) ---
    elif step == "wait_bc_text" and user_id == ADMIN_ID:
        photo = context.user_data.get("bc_photo")
        count = 0
        for uid in db["users"]:
            try:
                if photo:
                    await context.bot.send_photo(uid, photo, caption=text, parse_mode="Markdown")
                else:
                    await context.bot.send_message(uid, text, parse_mode="Markdown")
                count += 1
            except: pass
        await update.message.reply_text(f"✅ تم إرسال الإعلان لـ {count} مستخدم!")
        context.user_data.clear()

# ==========================================
# 6. PHOTO HANDLER (معالجة الصور للإعلانات)
# ==========================================
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID and context.user_data.get("step") == "wait_bc_photo":
        context.user_data["bc_photo"] = update.message.photo[-1].file_id
        context.user_data["step"] = "wait_bc_text"
        await update.message.reply_text("✅ الصورة دازت. دابا صيفط النص ديال الإعلان:")

# ==========================================
# 7. MAIN START COMMAND & SERVER
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u = get_user(user_id, update.effective_user.first_name)
    
    if u["is_banned"]:
        await update.message.reply_text("❌ تم حظرك من استخدام النظام.") ; return
    if not db["bot_status"] and user_id != ADMIN_ID:
        await update.message.reply_text("⚠️ النظام حالياً تحت الصيانة (Maintenance).") ; return
        
    txt, kb = main_menu(user_id)
    await update.message.reply_text(txt, reply_markup=kb, parse_mode="Markdown")

flask_app = Flask('')
@flask_app.route('/')
def home(): return "NOVA V6 MAX IS RUNNING SMOOTHLY!"

def run_bot():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    print("🌟 NOVA TV V6 MAX (THE ULTIMATE EDITION) IS ONLINE 🌟")
    app.run_polling()

if __name__ == "__main__":
    Thread(target=lambda: flask_app.run(host='0.0.0.0', port=8080)).start()
    run_bot()
