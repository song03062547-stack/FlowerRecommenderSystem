# 🌸 Flower Recommender System

ระบบแนะนำดอกไม้ด้วย Graph Database (Neo4j AuraDB) + Streamlit

## โครงสร้าง Graph
```
(:User {name})
(:Flower {name, meaning, image_url})
(User)-[:PREFERS {rating: 1-5}]->(Flower)
```

## ฟีเจอร์
**หน้าผู้ใช้ทั่วไป**
- เลือกชื่อที่มีอยู่ หรือพิมพ์ชื่อใหม่ (ระบบสร้าง User ให้อัตโนมัติ)
- ⭐ บันทึกดอกไม้ที่ชอบด้วยตัวเอง (ให้คะแนน 1–5)
- 📖 ดูประวัติดอกไม้ที่เคยให้คะแนนไว้ พร้อมรูปภาพและความหมาย
- 👥 ดูผู้ใช้คนอื่นที่มีรสนิยมใกล้เคียงกัน
- 🎯 ดอกไม้แนะนำเฉพาะบุคคล (Graph Collaborative Filtering) — ผู้ใช้ใหม่ไม่มีประวัติจะได้ดอกไม้สุ่ม 3 ชนิดแทน
- 🎲 สุ่มดอกไม้แนะนำประจำวัน

**หน้า Admin** (มีรหัสผ่าน)
- ดูรายการดอกไม้ทั้งหมด
- เพิ่ม / แก้ไข / ลบ ดอกไม้
- จัดการผู้ใช้แบบครบ CRUD: **เพิ่ม / แก้ไขชื่อ (rename) / ลบ** ผู้ใช้
- Setup ข้อมูลเริ่มต้น (10 Users / 13 Flowers) ด้วยปุ่มเดียว

## รันในเครื่อง (ทดสอบก่อน deploy)
```bash
pip install -r requirements.txt
mkdir -p .streamlit
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# แก้ไข .streamlit/secrets.toml ใส่ URI/Username/Password ของ Neo4j Aura จริง
streamlit run app.py
```

## Deploy ขึ้น GitHub + Streamlit Community Cloud

1. สร้าง repository ใหม่บน GitHub (หรือใช้ของเดิม) แล้ว push โฟลเดอร์นี้ทั้งหมดขึ้นไป
   ```bash
   git init
   git add .
   git commit -m "Flower Recommender System"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<your-repo>.git
   git push -u origin main
   ```
   **ห้าม push ไฟล์ `.streamlit/secrets.toml` ตัวจริงขึ้น GitHub** (มีแค่ `.example` เท่านั้นที่ควร push)

2. ไปที่ https://share.streamlit.io -> New app -> เลือก repo/branch นี้ -> Main file path: `app.py`

3. ก่อนกด Deploy ให้ไปที่ **Advanced settings -> Secrets** แล้ววางเนื้อหาแบบนี้ (ใส่ค่าจริงของคุณ):
   ```toml
   [neo4j]
   uri = "neo4j+s://xxxxxxxx.databases.neo4j.io"
   username = "neo4j"
   password = "รหัสผ่านจริงของ Aura instance"
   database = "neo4j"

   [admin]
   password = "รหัสผ่าน Admin ที่คุณตั้งเอง"
   ```

4. กด Deploy แล้วรอสักครู่ เว็บจะมีลิงก์ให้ใช้งานได้ทันที

5. เข้าเว็บ -> เมนู "เข้าสู่ระบบ Admin" -> กรอกรหัสผ่าน Admin -> เลือก "Setup ข้อมูลเริ่มต้น (Demo Data)" -> กดปุ่มสร้างข้อมูล (ทำครั้งแรกครั้งเดียวพอ ปลอดภัยถ้ากดซ้ำ)

6. กลับไปหน้าผู้ใช้ทั่วไป เลือกหรือพิมพ์ชื่อ แล้วทดลองใช้งานได้เลย

## รูปภาพดอกไม้
รูปอยู่ในโฟลเดอร์ `images/` ของ repo นี้เอง ถูกอ้างอิงผ่าน URL แบบ
`https://raw.githubusercontent.com/<your-username>/<your-repo>/main/images/<ชื่อไฟล์>.jpg`
**ถ้าคุณ push ขึ้นคนละ repo/username** ให้แก้ค่า `IMAGE_BASE_URL` ที่ต้นไฟล์ `app.py` ให้ตรงกับ repo จริงของคุณก่อน deploy
