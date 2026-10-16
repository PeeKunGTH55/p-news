# Daily News Briefing Bot (p-news)

ระบบบอทรายงานและสรุปข่าวประจำวันอัตโนมัติ (ภาษาไทย) ส่งตรงเข้า Telegram ทุกวันเวลา **10:00 น. (เวลาไทย)** ทำงานแบบ **Stateless** และใช้เครื่องมือ **ฟรี 100%** (Python 3.12 + RSS Feeds + Google Gemini API Free Tier + GitHub Actions)

---

## โครงสร้างโปรเจกต์ (Directory Structure)

```text
p-news/
├── .github/
│   └── workflows/
│       └── daily-briefing.yml        # GitHub Actions ตั้งเวลารัน 10:00 น. เวลาไทย (03:00 UTC)
├── config/
│   └── feeds.yaml                    # รายการ RSS Feed Sources แยกตาม 3 หมวดหมู่
├── docs/
│   ├── adr/
│   │   └── 0001-stateless-briefing-pipeline.md
│   └── agents/
├── src/
│   ├── __init__.py
│   ├── domain.py                     # โมเดลโดเมนและตรรกะ PublicationWindow (00:00-10:00 + Fallback 21:00)
│   ├── config.py                     # โหลดค่า Environment Variables และไฟล์ feeds.yaml
│   ├── collector.py                  # ดึง RSS, แปลงโซนเวลาเป็น Asia/Bangkok, กรองเวลาและตัดข่าวซ้ำ
│   ├── curator.py                    # เรียก Gemini API ครั้งเดียว (Structured JSON) คัดเลือกและสรุปข่าวไม่ซ้ำหมวด
│   ├── formatter.py                  # จัดรูปแบบ Telegram HTML และแบ่งข้อความอัตโนมัติเมื่อเกิน 4,096 ตัวอักษร
│   ├── notifier.py                   # ส่งข้อความผ่าน Telegram Bot HTTP API
│   └── main.py                       # จุดเริ่มต้นโปรแกรม (รองรับ --dry-run)
├── tests/
│   └── test_pipeline.py              # Unit Tests ตรวจสอบการกรองเวลา, Fallback และการแบ่งข้อความ
├── .env.example                      # ตัวอย่างไฟล์ตั้งค่าตัวแปรสภาพแวดล้อม
├── GLOSSARY.md                       # นิยามศัพท์โดเมนของโปรเจกต์
└── requirements.txt                  # รายการแพ็กเกจ Python
```

---

## วิธีตั้งค่า Telegram Bot และ API Keys

### 1. ขอ Google Gemini API Key (ฟรี)
1. ไปที่ [Google AI Studio](https://aistudio.google.com/app/apikey)
2. กด **Create API key** และคัดลอกค่าเก็บไว้ใส่ใน `GEMINI_API_KEY`
3. โมเดลเริ่มต้นคือ `gemini-2.5-flash` (สามารถเปลี่ยนผ่านตัวแปร `GEMINI_MODEL` ได้ตลอดโดยไม่ต้องแก้โค้ด)

### 2. สร้าง Telegram Bot (ผ่าน BotFather)
1. เปิดแอป Telegram ค้นหา **`@BotFather`** (สังเกตเครื่องหมายติ๊กถูกสีฟ้า)
2. พิมพ์คำสั่ง `/newbot`
3. ตั้งชื่อที่แสดงของบอท (เช่น `Daily News Briefing`)
4. ตั้ง Username ของบอท โดยต้องลงท้ายด้วย `bot` (เช่น `my_daily_pnews_bot`)
5. **BotFather** จะส่ง **HTTP API Token** กลับมา (รูปแบบ `123456789:ABCdefGHI...`) ให้คัดลอกเก็บไว้เป็นค่า `TELEGRAM_BOT_TOKEN`

### 3. หาค่า `TELEGRAM_CHAT_ID`
- **กรณีส่งเข้าแชทส่วนตัว**:
  1. กดลิงก์บอทที่เพิ่งสร้างแล้วกดปุ่ม **Start** (หรือส่งข้อความอะไรก็ได้ 1 ข้อความหาบอท)
  2. เปิดเบราว์เซอร์เข้า URL ด้านล่างนี้ (แทนที่ `<YOUR_BOT_TOKEN>` ด้วย Token ของคุณ):
     ```text
     https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
     ```
  3. มองหา `"chat":{"id":123456789,...}` ตัวเลขใน `"id"` คือ `TELEGRAM_CHAT_ID` ของคุณ
- **กรณีส่งเข้ากลุ่ม (Group) หรือ Channel**:
  1. เชิญบอทเข้ากลุ่ม หรือเพิ่มบอทเป็น Admin ของ Channel
  2. ส่งข้อความทดสอบในกลุ่ม/Channel 1 ข้อความ แล้วเปิด `/getUpdates` ด้านบน
  3. ค่า `"chat":{"id":-1001234567890}` (มีเครื่องหมายลบนำหน้า) คือ `TELEGRAM_CHAT_ID`

---

## การติดตั้งและทดสอบรันบนเครื่อง (Local Setup)

1. สร้างและเปิดใช้งาน Virtual Environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\pip install -r requirements.txt
   ```
2. คัดลอกไฟล์ `.env.example` เป็น `.env` และกรอกค่าจริง:
   ```powershell
   Copy-Item .env.example .env
   ```
3. **ทดสอบรันโหมด `--dry-run`** (ดึงข่าวจริง + สรุปด้วย Gemini จริง แต่แสดงผลบนหน้าจอโดยไม่ส่งเข้า Telegram):
   ```powershell
   .\.venv\Scripts\python -m src.main --dry-run
   ```
4. **ทดสอบส่งเข้า Telegram จริง**:
   ```powershell
   .\.venv\Scripts\python -m src.main
   ```
5. **รันชุดทดสอบ (Unit Tests)**:
   ```powershell
   .\.venv\Scripts\pytest
   ```

---

## การตั้งค่ารันอัตโนมัติบน GitHub Actions (ฟรี 100%)

1. อัปโหลดโค้ดขึ้น GitHub Repository ของคุณ
2. ไปที่หน้า Repository บน GitHub -> **Settings** -> **Secrets and variables** -> **Actions**
3. ในแท็บ **Secrets** กด **New repository secret** เพื่อเพิ่ม 3 ค่านี้:
   - `GEMINI_API_KEY`: API Key จาก Google AI Studio
   - `TELEGRAM_BOT_TOKEN`: Token จาก `@BotFather`
   - `TELEGRAM_CHAT_ID`: Chat ID เป้าหมาย
4. *(ตัวเลือกเสริม)* หากต้องการเปลี่ยนชื่อโมเดลโดยไม่แก้โค้ด ให้ไปที่แท็บ **Variables** -> **New repository variable** แล้วสร้างตัวแปรชื่อ `GEMINI_MODEL` (หากไม่สร้าง ระบบจะใช้ `gemini-2.5-flash` เป็นค่าเริ่มต้น)
5. ทดสอบสั่งรันด้วยตัวเองได้ทันทีที่เมนู **Actions** -> เลือก **Daily News Briefing** -> กด **Run workflow**
