# Pre-market Stock Scanner

สแกนหุ้นสหรัฐฯ ที่ "เปิดช่องว่างขึ้น" (gap up) ในช่วงก่อนตลาดเปิด ทุกเช้าวันทำการ

## เงื่อนไขการคัดกรอง (ค่าเริ่มต้น)

| เงื่อนไข | ค่า |
|---|---|
| Gap จากราคาปิดวันก่อนหน้า | มากกว่า 5% |
| ราคาหุ้น | มากกว่า $3 |
| วอลุ่มช่วง pre-market | มากกว่า 50,000 หุ้น |

## แหล่งข้อมูล

- **Yahoo Finance** – รายชื่อหุ้นจาก screener (`day_gainers`, `small_cap_gainers`, `most_actives`, `aggressive_small_caps`) + หุ้น trending + `watchlist.txt`
  จากนั้นดึงกราฟ 1 นาทีที่รวมช่วง pre-market เพื่อคำนวณราคาล่าสุด, % gap และวอลุ่ม pre-market
- **Benzinga** – ข่าว catalyst ย่อเหลือ 1 ประโยค
  - ถ้าตั้ง `BENZINGA_API_KEY` จะใช้ Benzinga News API โดยตรง
  - ถ้าไม่มี key จะใช้ข่าวของ Benzinga ที่เผยแพร่บน Yahoo Finance แทน

## วิธีใช้

```bash
pip install -r requirements.txt
export BENZINGA_API_KEY=xxxx        # ไม่บังคับ
python -m premarket_scanner --watchlist watchlist.txt
```

ปรับเงื่อนไขได้: `--min-gap 5 --min-price 3 --min-volume 50000 --out-dir results`

### ตัวอย่างผลลัพธ์

```
PRE-MARKET GAP SCANNER — 2026-10-13
Ticker      Price    Gap %  Catalyst
------------------------------------------------------------------------------------------
GAP        $23.00  +15.00%  GAP soars after earnings beat.
BIG       $106.00   +6.00%  No recent Benzinga news catalyst found.
```

ผลแต่ละวันบันทึกเป็นไฟล์ใหม่ `results/premarket_scan_YYYY-MM-DD.json` (วันที่ตามเวลานิวยอร์ก):

```json
{
  "date": "2026-10-13",
  "generated_at": "2026-10-13T08:45:12-04:00",
  "criteria": {"min_gap_percent": 5.0, "min_price": 3.0, "min_premarket_volume": 50000},
  "count": 1,
  "results": [
    {"ticker": "GAP", "price": 23.0, "previous_close": 20.0, "gap_percent": 15.0,
     "premarket_volume": 80000, "catalyst": "GAP soars after earnings beat.",
     "news_headline": "...", "news_url": "...", "news_source": "Benzinga via Yahoo Finance"}
  ]
}
```

## รันอัตโนมัติทุกเช้า

`.github/workflows/premarket-scan.yml` รันจันทร์–ศุกร์ เวลา 12:45 UTC
(8:45 น. ET ช่วงฤดูร้อน / 7:45 น. ET ช่วงฤดูหนาว — ตรงกับ 19:45 น. เวลาไทย) แล้ว commit ไฟล์ JSON กลับเข้า repo
ถ้ามี Benzinga API key ให้เพิ่มเป็น repository secret ชื่อ `BENZINGA_API_KEY`
สั่งรันเองได้จากแท็บ Actions → "Pre-market scan" → Run workflow

## ทดสอบ

```bash
pip install -r requirements-dev.txt
pytest
```

> หมายเหตุ: Yahoo Finance endpoint ที่ใช้เป็น API ไม่เป็นทางการ อาจเปลี่ยนแปลงหรือจำกัดการเรียกได้
