import sqlite3
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes, 
    MessageHandler, filters, ConversationHandler, CallbackQueryHandler
)

TOKEN = ""

# وضعیت‌های گفتگوها
GET_DATE, GET_TIME = range(2)
GET_BIO = range(1)

# ==================== بخش دیتابیس هوشمند ====================
def init_db():
    conn = sqlite3.connect("clinic.db")
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        username TEXT,
        first_name TEXT,
        role TEXT DEFAULT 'patient'
    )
    """)
    
    # ساخت جدول روانشناسان با ساختار اولیه
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS therapists (
        user_id INTEGER PRIMARY KEY,
        card_number TEXT,
        clinic_address TEXT
    )
    """)
    
    # تزریق خودکار و هوشمند ستون bio_text اگر وجود نداشته باشد (حل قطعی ارور)
    try:
        cursor.execute("ALTER TABLE therapists ADD COLUMN bio_text TEXT DEFAULT 'هنوز معرفی ثبت نشده است.'")
    except sqlite3.OperationalError:
        pass  # ستون از قبل وجود دارد و مشکلی نیست
        
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS time_slots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        therapist_id INTEGER,
        slot_date TEXT,
        slot_time TEXT,
        status TEXT DEFAULT 'available',
        patient_id INTEGER,
        receipt_file_id TEXT
    )
    """)
    conn.commit()
    conn.close()
    print("🗄️ دیتابیس اصلاح و ستون‌های گمشده به صورت خودکار تزریق شدند.")

def save_user_to_db(telegram_id, username, first_name):
    conn = sqlite3.connect("clinic.db")
    cursor = conn.cursor()
    role = 'patient'
    try:
        cursor.execute("INSERT INTO users (telegram_id, username, first_name, role) VALUES (?, ?, ?, 'patient')", (telegram_id, username, first_name))
        conn.commit()
    except sqlite3.IntegrityError:
        cursor.execute("SELECT role FROM users WHERE telegram_id = ?", (telegram_id,))
        res = cursor.fetchone()
        if res: role = res[0]
    finally:
        conn.close()
    return role

def make_user_therapist(telegram_id):
    conn = sqlite3.connect("clinic.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET role = 'therapist' WHERE telegram_id = ?", (telegram_id,))
    cursor.execute("INSERT OR IGNORE INTO therapists (user_id) VALUES (?)", (telegram_id,))
    conn.commit()
    conn.close()

def update_therapist_bio(therapist_id, bio_text):
    conn = sqlite3.connect("clinic.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO therapists (user_id, bio_text) VALUES (?, ?)", (therapist_id, bio_text))
    conn.commit()
    conn.close()

def get_therapist_bio():
    conn = sqlite3.connect("clinic.db")
    cursor = conn.cursor()
    cursor.execute("SELECT bio_text FROM therapists ORDER BY user_id DESC LIMIT 1")
    res = cursor.fetchone()
    conn.close()
    return res[0] if (res and res[0]) else "هنوز معرفی برای پزشک ثبت نشده است."

def add_time_slot(therapist_id, date, time):
    conn = sqlite3.connect("clinic.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO time_slots (therapist_id, slot_date, slot_time, status) VALUES (?, ?, ?, 'available')", (therapist_id, date, time))
    conn.commit()
    conn.close()

def get_available_slots():
    conn = sqlite3.connect("clinic.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, slot_date, slot_time FROM time_slots WHERE status = 'available'")
    slots = cursor.fetchall()
    conn.close()
    return slots

def reserve_slot_temporary(slot_id, patient_id):
    conn = sqlite3.connect("clinic.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE time_slots SET status = 'pending', patient_id = ? WHERE id = ?", (patient_id, slot_id))
    conn.commit()
    conn.close()

def save_receipt_and_get_details(patient_id, file_id):
    conn = sqlite3.connect("clinic.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, therapist_id, slot_date, slot_time FROM time_slots WHERE patient_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1", (patient_id,))
    slot = cursor.fetchone()
    if slot:
        slot_id, therapist_id, date, time = slot
        cursor.execute("UPDATE time_slots SET receipt_file_id = ? WHERE id = ?", (file_id, slot_id))
        conn.commit()
        conn.close()
        return slot_id, therapist_id, date, time
    conn.close()
    return None

def update_slot_status(slot_id, new_status):
    conn = sqlite3.connect("clinic.db")
    cursor = conn.cursor()
    cursor.execute("SELECT patient_id, slot_date, slot_time FROM time_slots WHERE id = ?", (slot_id,))
    details = cursor.fetchone()
    if new_status == 'available':
        cursor.execute("UPDATE time_slots SET status = 'available', patient_id = NULL, receipt_file_id = NULL WHERE id = ?", (slot_id,))
    else:
        cursor.execute("UPDATE time_slots SET status = ? WHERE id = ?", (new_status, slot_id))
    conn.commit()
    conn.close()
    return details
# =============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    tg_user = update.effective_user
    user_role = save_user_to_db(tg_user.id, tg_user.username, tg_user.first_name)
    
    if user_role == 'therapist':
        keyboard = [['تعریف ساعت کاری', 'تنظیم پروفایل معرفی'], ['وضعیت اشتراک']]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(f"سلام دکتر {tg_user.first_name} عزیز. به پنل خود خوش آمدید.", reply_markup=reply_markup)
    else:
        keyboard = [['مشاهده تایم‌های خالی', 'آشنایی با پزشک'], ['نوبت‌های من', 'ارتباط با پشتیبانی']]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(f"سلام {tg_user.first_name} عزیز! به ربات نوبت‌دهی خوش آمدید.", reply_markup=reply_markup)

async def show_slots_to_patient(update: Update, context: ContextTypes.DEFAULT_TYPE):
    slots = get_available_slots()
    if not slots:
        await update.message.reply_text("در حال حاضر هیچ زمان خالی توسط پزشک تعریف نشده است.")
        return
    keyboard = [[InlineKeyboardButton(f"📅 {d} - ⏰ ساعت {t}", callback_data=f"reserve_{s_id}")] for s_id, d, t in slots]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("لطفاً یکی از زمان‌های خالی زیر را جهت نوبت‌دهی انتخاب کنید:", reply_markup=reply_markup)

async def show_doctor_bio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bio = get_therapist_bio()
    await update.message.reply_text(f"📝 **پروفایل و معرفی پزشک:**\n\n{bio}")

# --- گفتگو تنظیم بیوگرافی ---
async def start_set_bio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "لطفاً متن معرفی، رزومه و سوابق خود را ارسال کنید:\n(برای انصراف /cancel را بزنید)",
        reply_markup=ReplyKeyboardRemove()
    )
    return GET_BIO

async def get_bio_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    therapist_id = update.effective_user.id
    bio_text = update.message.text
    
    update_therapist_bio(therapist_id, bio_text)
    
    keyboard = [['تعریف ساعت کاری', 'تنظیم پروفایل معرفی'], ['وضعیت اشتراک']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("✅ پروفایل معرفی شما با موفقیت به‌روزرسانی شد.", reply_markup=reply_markup)
    return ConversationHandler.END

async def cancel_bio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات لغو شد.")
    return ConversationHandler.END

async def set_doctor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = update.effective_user
    make_user_therapist(tg_user.id)
    await update.message.reply_text("🎉 حساب شما با موفقیت به نقش 'درمانگر' ارتقا یافت. دوباره دستور /start را بزنید.")

async def inline_buttons_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data.startswith("reserve_"):
        slot_id = int(data.split("_")[1])
        patient_id = query.from_user.id
        try:
            reserve_slot_temporary(slot_id, patient_id)
            text_reply = (
                "📌 این تایم به مدت ۵ ساعت برای شما رزرو موقت شد.\n\n"
                "💳 لطفاً مبلغ ویزیت را به شماره کارت زیر واریز کنید:\n`۶۰۳۷-۹۹۹۹-۹۹۹۹-۹۹۹۹`\n\n"
                "سپس **عکس فیش واریزی** خود را ارسال کنید."
            )
            await query.edit_message_text(text=text_reply, parse_mode="Markdown")
        except Exception as e:
            await query.edit_message_text(text=f"❌ خطای سیستم: {e}")

    elif data.startswith("approve_"):
        slot_id = int(data.split("_")[1])
        patient_id, date, time = update_slot_status(slot_id, 'booked')
        await query.edit_message_caption(caption=f"✅ **این نوبت با موفقیت تایید قطعی شد.**\n\n📅 تاریخ: {date}\n⏰ ساعت: {time}", reply_markup=None)
        try:
            await context.bot.send_message(chat_id=patient_id, text=f"🎉 **مراجع گرامی، نوبت شما قطعی شد!**\n\n📅 تاریخ جلسه: {date}\n⏰ ساعت جلسه: {time}")
        except Exception as e:
            print(e)

    elif data.startswith("reject_"):
        slot_id = int(data.split("_")[1])
        patient_id, date, time = update_slot_status(slot_id, 'available')
        await query.edit_message_caption(caption=f"❌ **فیش واریزی رد شد.**\n\n📅 تاریخ: {date}\n⏰ ساعت: {time}", reply_markup=None)
        try:
            await context.bot.send_message(chat_id=patient_id, text=f"⚠️ **مراجع گرامی، فیش واریزی شما توسط پزشک رد شد.**")
        except Exception as e:
            print(e)

async def receive_receipt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    patient = update.effective_user
    photo_file_id = update.message.photo[-1].file_id
    result = save_receipt_and_get_details(patient.id, photo_file_id)
    if result is None:
        await update.message.reply_text("❌ شما در حال حاضر هیچ نوبت معلقی برای ارسال فیش ندارید.")
        return
    slot_id, therapist_id, date, time = result
    await update.message.reply_text("✅ فیش شما دریافت شد و برای پزشک ارسال گردید.")
    
    doc_keyboard = [[InlineKeyboardButton("✅ تایید نوبت", callback_data=f"approve_{slot_id}"), InlineKeyboardButton("❌ رد فیش", callback_data=f"reject_{slot_id}")]]
    doc_reply_markup = InlineKeyboardMarkup(doc_keyboard)
    await context.bot.send_photo(chat_id=therapist_id, photo=photo_file_id, caption=f"🔔 **رسید جدید دریافت شد!**\n\n👤 مراجع: {patient.first_name}\n📅 تاریخ: {date}\n⏰ ساعت: {time}", reply_markup=doc_reply_markup)

# --- گفتگو تعریف ساعت کاری ---
async def start_add_slot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لطفاً تاریخ روزی که مایل به تعریف نوبت هستید را وارد کنید:", reply_markup=ReplyKeyboardRemove())
    return GET_DATE

async def get_date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['selected_date'] = update.message.text
    await update.message.reply_text("حالا ساعت دقیق را وارد کنید:")
    return GET_TIME

async def get_time_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    therapist_id = update.effective_user.id
    date = context.user_data['selected_date']
    time = update.message.text
    add_time_slot(therapist_id, date, time)
    keyboard = [['تعریف ساعت کاری', 'تنظیم پروفایل معرفی'], ['وضعیت اشتراک']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(f"✅ تایم خالی جدید ثبت شد.", reply_markup=reply_markup)
    return ConversationHandler.END

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    
    add_slot_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Text("تعریف ساعت کاری"), start_add_slot)],
        states={
            GET_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date_handler)],
            GET_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_time_handler)],
        },
        fallbacks=[],
    )
    
    set_bio_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Text("تنظیم پروفایل معرفی"), start_set_bio)],
        states={
            GET_BIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_bio_handler)]
        },
        fallbacks=[CommandHandler("cancel", cancel_bio)]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("iamdoctor", set_doctor))
    app.add_handler(add_slot_conv)
    app.add_handler(set_bio_conv)
    
    app.add_handler(MessageHandler(filters.Text("مشاهده تایم‌های خالی"), show_slots_to_patient))
    app.add_handler(MessageHandler(filters.Text("آشنایی با پزشک"), show_doctor_bio))
    app.add_handler(MessageHandler(filters.PHOTO, receive_receipt_handler))
    app.add_handler(CallbackQueryHandler(inline_buttons_handler))
    
    print("ربات کاملاً اصلاح‌شده بدون خطا روشن شد...")
    app.run_polling()

if __name__ == "__main__":
    main()
    .