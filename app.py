import streamlit as st
from neo4j import GraphDatabase
import pandas as pd

# ==========================================
# PAGE CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="ระบบแนะนำดอกไม้ (Flower Recommender)",
    page_icon="🌸",
    layout="wide"
)

ADMIN_PASSWORD = st.secrets.get("admin", {}).get("password", "admin1234")

# ==========================================
# NEO4J DATABASE FUNCTIONS
# ==========================================
@st.cache_resource
def get_driver():
    """เชื่อมต่อกับ Neo4j AuraDB โดยอ่านค่าจาก Streamlit Secrets"""
    uri = st.secrets["neo4j"]["uri"]
    username = st.secrets["neo4j"]["username"]
    password = st.secrets["neo4j"]["password"]

    driver = GraphDatabase.driver(uri, auth=(username, password))
    driver.verify_connectivity()
    return driver


def query(cypher_query, parameters=None, write=False):
    """ฟังก์ชันกลางในการส่งคำสั่ง Cypher Query ไปยัง Neo4j"""
    driver = get_driver()
    db_name = st.secrets["neo4j"].get("database", "neo4j")

    with driver.session(database=db_name) as session:
        if write:
            result = session.execute_write(lambda tx: tx.run(cypher_query, parameters).data())
        else:
            result = session.execute_read(lambda tx: tx.run(cypher_query, parameters).data())
    return result


def ping():
    """ทดสอบการเชื่อมต่อกับ Neo4j"""
    try:
        res = query("RETURN 1 AS ok")
        return res[0]["ok"] == 1
    except Exception:
        return False


# ----------------- USER FUNCTIONS -----------------

def get_all_users():
    """ดึงรายชื่อ User ทั้งหมดที่มีในระบบ"""
    cypher = "MATCH (u:User) RETURN u.name AS name ORDER BY name"
    res = query(cypher)
    return [r["name"] for r in res]


def get_user_preferred_flowers(username):
    """ดึงรายการดอกไม้ที่ผู้ใช้คนนี้เคยเลือก/ชอบไว้ พร้อมคะแนน"""
    cypher = """
    MATCH (u:User {name: $username})-[r:PREFERS]->(f:Flower)
    RETURN
        f.name AS flower,
        f.meaning AS meaning,
        f.image_url AS image_url,
        r.rating AS rating
    ORDER BY rating DESC, flower
    """
    res = query(cypher, {"username": username})
    return pd.DataFrame(res)


def get_similar_users(target_user):
    """หาผู้ใช้คนอื่นที่มีรสนิยมใกล้เคียงกัน (ชอบดอกไม้เดียวกันอย่างน้อย 1 ชนิด)"""
    cypher = """
    MATCH (me:User {name: $target_user})-[r1:PREFERS]->(f:Flower)<-[r2:PREFERS]-(other:User)
    WHERE other <> me
    RETURN
        other.name AS similar_user,
        f.name AS flower,
        f.meaning AS meaning,
        f.image_url AS image_url,
        r2.rating AS other_rating
    ORDER BY similar_user, flower
    """
    res = query(cypher, {"target_user": target_user})
    return pd.DataFrame(res)


def get_random_recommended_flower():
    """สุ่มดอกไม้ 1 ชนิดพร้อมความหมายและรูปภาพ"""
    cypher = """
    MATCH (f:Flower)
    RETURN f.name AS name, f.meaning AS meaning, f.image_url AS image_url
    ORDER BY rand()
    LIMIT 1
    """
    res = query(cypher)
    return res[0] if res else None


def get_or_create_user(username):
    """สร้างโหนด User ใหม่ถ้ายังไม่มีในระบบ (ปลอดภัยต่อการเรียกซ้ำ เพราะใช้ MERGE)"""
    cypher = "MERGE (u:User {name: $username}) RETURN u.name AS name"
    query(cypher, {"username": username}, write=True)


def add_user_preference(username, flower_name, rating):
    """เพิ่ม/อัปเดตความสัมพันธ์ PREFERS ระหว่าง User กับ Flower"""
    cypher = """
    MATCH (u:User {name: $username}), (f:Flower {name: $flower_name})
    MERGE (u)-[r:PREFERS]->(f)
    SET r.rating = $rating
    """
    query(cypher, {"username": username, "flower_name": flower_name, "rating": rating}, write=True)


def recommend_flowers_for_user(target_user):
    """คำนวณดอกไม้แนะนำอ้างอิงตามรสนิยม หรือสุ่มให้หากยังไม่มีประวัติ"""
    check_cypher = "MATCH (u:User {name: $target_user})-[:PREFERS]->(f:Flower) RETURN count(f) AS count"
    user_pref_count = query(check_cypher, {"target_user": target_user})[0]["count"]

    if user_pref_count > 0:
        # หากมีประวัติ ให้แนะนำตาม Graph Collaborative Filtering
        cypher = """
        MATCH (me:User {name: $target_user})-[:PREFERS]->(liked:Flower)
        MATCH (liked)<-[:PREFERS]-(similar:User)-[r:PREFERS]->(rec:Flower)
        WHERE similar <> me AND NOT (me)-[:PREFERS]->(rec)
        RETURN
            rec.name AS flower,
            rec.meaning AS meaning,
            rec.image_url AS image_url,
            sum(r.rating) AS score
        ORDER BY score DESC, flower
        LIMIT 6
        """
        res = query(cypher, {"target_user": target_user})
        return pd.DataFrame(res)
    else:
        # หากเป็นผู้ใช้ใหม่ สุ่มดอกไม้ขึ้นมาให้ 3 ชนิด
        cypher = """
        MATCH (f:Flower)
        RETURN
            f.name AS flower,
            f.meaning AS meaning,
            f.image_url AS image_url,
            5 AS score
        ORDER BY rand()
        LIMIT 3
        """
        res = query(cypher)
        return pd.DataFrame(res)


# ----------------- ADMIN CRUD FUNCTIONS -----------------

def get_all_flowers():
    """ดึงรายการดอกไม้ทั้งหมด"""
    cypher = "MATCH (f:Flower) RETURN f.name AS name, f.meaning AS meaning, f.image_url AS image_url ORDER BY name"
    return pd.DataFrame(query(cypher))


def add_flower(name, meaning, image_url):
    """เพิ่มดอกไม้ใหม่"""
    cypher = """
    MERGE (f:Flower {name: $name})
    SET f.meaning = $meaning, f.image_url = $image_url
    """
    query(cypher, {"name": name, "meaning": meaning, "image_url": image_url}, write=True)


def update_flower(name, new_meaning, new_image_url):
    """แก้ไขข้อมูลดอกไม้"""
    cypher = """
    MATCH (f:Flower {name: $name})
    SET f.meaning = $new_meaning, f.image_url = $new_image_url
    """
    query(cypher, {"name": name, "new_meaning": new_meaning, "new_image_url": new_image_url}, write=True)


def delete_flower(name):
    """ลบดอกไม้และความสัมพันธ์ทั้งหมด"""
    cypher = """
    MATCH (f:Flower {name: $name})
    DETACH DELETE f
    """
    query(cypher, {"name": name}, write=True)


def delete_user(name):
    """ลบผู้ใช้และความสัมพันธ์ทั้งหมดของเขา"""
    cypher = "MATCH (u:User {name: $name}) DETACH DELETE u"
    query(cypher, {"name": name}, write=True)


def add_user(name):
    """เพิ่มผู้ใช้ใหม่ (Admin เป็นคนเพิ่มเอง) — ปลอดภัยต่อการกดซ้ำเพราะใช้ MERGE"""
    cypher = "MERGE (u:User {name: $name})"
    query(cypher, {"name": name}, write=True)


def rename_user(old_name, new_name):
    """แก้ไข/เปลี่ยนชื่อผู้ใช้ โดยความสัมพันธ์เดิมทั้งหมดยังติดไปกับ node เดิม"""
    cypher = "MATCH (u:User {name: $old_name}) SET u.name = $new_name"
    query(cypher, {"old_name": old_name, "new_name": new_name}, write=True)


IMAGE_BASE_URL = "https://raw.githubusercontent.com/song03062547-stack/FlowerRecommenderSystem/main/images/"


def seed_demo_data():
    """สร้าง Constraint และลงข้อมูลเริ่มต้น (10 Users / 13 Flowers) พร้อมผูกรูปจาก GitHub
    ปลอดภัยต่อการกดซ้ำ — ใช้ MERGE ทั้งหมด จึงไม่สร้างข้อมูลซ้ำ"""
    query("CREATE CONSTRAINT user_name_unique IF NOT EXISTS FOR (u:User) REQUIRE u.name IS UNIQUE", write=True)
    query("CREATE CONSTRAINT flower_name_unique IF NOT EXISTS FOR (f:Flower) REQUIRE f.name IS UNIQUE", write=True)

    users = ["Praew", "Kaew", "Miu", "Fon", "Palm", "Joy", "Top", "Nook", "Game", "Bow"]
    query("UNWIND $users AS name MERGE (u:User {name: name})", {"users": users}, write=True)

    flowers = [
        {"name": "Jasmine", "meaning": "ความรักอันบริสุทธิ์ ความกตัญญู", "image_url": IMAGE_BASE_URL + "jasmine.jpg"},
        {"name": "Pink Rose", "meaning": "ความรักอันอ่อนโยน ความขอบคุณ", "image_url": IMAGE_BASE_URL + "Pink%20Rose.jpg"},
        {"name": "Lotus", "meaning": "ความบริสุทธิ์ การหลุดพ้นจากกิเลส", "image_url": IMAGE_BASE_URL + "Lotus.jpg"},
        {"name": "Sunflower", "meaning": "ความหวัง พลังบวก", "image_url": IMAGE_BASE_URL + "Sunflower.jpg"},
        {"name": "White Lily", "meaning": "ความบริสุทธิ์ เกียรติยศ", "image_url": IMAGE_BASE_URL + "White%20Lily.jpg"},
        {"name": "Purple Orchid", "meaning": "ความสง่างาม เสน่ห์", "image_url": IMAGE_BASE_URL + "Purple%20Orchid.jpg"},
        {"name": "Chrysanthemum", "meaning": "ความสัตย์ซื่อ อายุยืนยาว", "image_url": IMAGE_BASE_URL + "Chrysanthemum.jpg"},
        {"name": "Red Carnation", "meaning": "ความรักของแม่", "image_url": IMAGE_BASE_URL + "Red%20Carnation.jpg"},
        {"name": "Blue Iris", "meaning": "ปัญญา ความหวัง ศรัทธา", "image_url": IMAGE_BASE_URL + "Blue%20Iris.jpg"},
        {"name": "Red Tulip", "meaning": "ความรักที่สมบูรณ์แบบ", "image_url": IMAGE_BASE_URL + "Red%20Tulip.jpg"},
        {"name": "Daisy", "meaning": "ความรักบริสุทธิ์ ความสดใสไร้เดียงสา", "image_url": IMAGE_BASE_URL + "Daisy.jpg"},
        {"name": "Hydrangea", "meaning": "ความเข้าใจ การขอบคุณจากหัวใจ", "image_url": IMAGE_BASE_URL + "Hydrangea.jpg"},
        {"name": "Peony", "meaning": "ความมั่งคั่ง เกียรติยศ และความรักที่งดงาม", "image_url": IMAGE_BASE_URL + "Peony.jpg"},
    ]
    query("""
    UNWIND $flowers AS row
    MERGE (f:Flower {name: row.name})
    SET f.meaning = row.meaning, f.image_url = row.image_url
    """, {"flowers": flowers}, write=True)

    preferences = [
        {"user": "Praew", "flower": "Jasmine", "rating": 5},
        {"user": "Praew", "flower": "Pink Rose", "rating": 4},
        {"user": "Praew", "flower": "Lotus", "rating": 3},
        {"user": "Kaew", "flower": "Jasmine", "rating": 4},
        {"user": "Kaew", "flower": "Pink Rose", "rating": 5},
        {"user": "Kaew", "flower": "Sunflower", "rating": 3},
        {"user": "Kaew", "flower": "White Lily", "rating": 4},
        {"user": "Miu", "flower": "Lotus", "rating": 5},
        {"user": "Miu", "flower": "Purple Orchid", "rating": 4},
        {"user": "Miu", "flower": "Chrysanthemum", "rating": 3},
        {"user": "Miu", "flower": "Peony", "rating": 4},
        {"user": "Fon", "flower": "Sunflower", "rating": 5},
        {"user": "Fon", "flower": "White Lily", "rating": 4},
        {"user": "Fon", "flower": "Blue Iris", "rating": 4},
        {"user": "Fon", "flower": "Red Tulip", "rating": 3},
        {"user": "Palm", "flower": "Purple Orchid", "rating": 5},
        {"user": "Palm", "flower": "Chrysanthemum", "rating": 4},
        {"user": "Palm", "flower": "Red Carnation", "rating": 5},
        {"user": "Palm", "flower": "Peony", "rating": 5},
        {"user": "Joy", "flower": "Daisy", "rating": 5},
        {"user": "Joy", "flower": "Pink Rose", "rating": 4},
        {"user": "Joy", "flower": "Jasmine", "rating": 3},
        {"user": "Top", "flower": "Daisy", "rating": 4},
        {"user": "Top", "flower": "Hydrangea", "rating": 5},
        {"user": "Top", "flower": "Sunflower", "rating": 3},
        {"user": "Nook", "flower": "Hydrangea", "rating": 4},
        {"user": "Nook", "flower": "Blue Iris", "rating": 5},
        {"user": "Game", "flower": "Red Tulip", "rating": 4},
        {"user": "Game", "flower": "Daisy", "rating": 3},
        {"user": "Game", "flower": "Red Carnation", "rating": 4},
        {"user": "Bow", "flower": "Hydrangea", "rating": 3},
        {"user": "Bow", "flower": "White Lily", "rating": 5},
        {"user": "Bow", "flower": "Purple Orchid", "rating": 4},
    ]
    query("""
    UNWIND $preferences AS row
    MATCH (u:User {name: row.user}), (f:Flower {name: row.flower})
    MERGE (u)-[r:PREFERS]->(f)
    SET r.rating = row.rating
    """, {"preferences": preferences}, write=True)


# ==========================================
# STREAMLIT UI INTERFACE
# ==========================================

# ตรวจสอบการเชื่อมต่อฐานข้อมูลก่อนแสดงผลทุกหน้า
try:
    connected = ping()
except Exception as exc:
    connected = False
    st.error("❌ ไม่สามารถเชื่อมต่อฐานข้อมูล Neo4j ได้")
    st.exception(exc)

if not connected:
    st.error("❌ ไม่สามารถเชื่อมต่อฐานข้อมูล Neo4j ได้ โปรดตรวจสอบ Secrets configuration บน Streamlit")
    st.code(
        '[neo4j]\nuri = "neo4j+s://YOUR_INSTANCE.databases.neo4j.io"\n'
        'username = "neo4j"\npassword = "YOUR_PASSWORD"\ndatabase = "neo4j"\n\n'
        '[admin]\npassword = "your-own-admin-password"',
        language="toml",
    )
    st.stop()

st.sidebar.title("🌸 เมนูใช้งาน")
menu = st.sidebar.radio("เลือกหน้าต่าง:", ["หน้าผู้ใช้ทั่วไป (User)", "เข้าสู่ระบบ Admin"])

# ------------------------------------------
# 1. หน้าผู้ใช้ทั่วไป (USER SIDE)
# ------------------------------------------
if menu == "หน้าผู้ใช้ทั่วไป (User)":
    st.title("🌸 ระบบแนะนำดอกไม้")
    st.caption("เลือกชื่อของคุณจากรายชื่อที่มีอยู่ หรือพิมพ์ชื่อใหม่เพื่อเริ่มใช้งานในฐานะผู้ใช้คนใหม่")

    col_sel, col_inp = st.columns(2)

    with col_sel:
        existing_users = get_all_users()
        selected_user = st.selectbox("📌 เลือกรายชื่อผู้ใช้ที่มีในระบบ:", ["-- เลือกจากรายชื่อ --"] + existing_users)

    with col_inp:
        input_user = st.text_input("👤 หรือ พิมพ์ชื่อของคุณเอง (เช่น Song):", placeholder="กรอกชื่อตรงนี้...")

    # ตัดสินใจว่าจะใช้ชื่อไหน (ถ้าพิมพ์ชื่อใหม่ให้ใช้ชื่อใหม่ ถ้าเลือกจากลิสต์ให้ใช้ชื่อที่เลือก)
    current_user = ""
    if input_user.strip() != "":
        current_user = input_user.strip()
    elif selected_user != "-- เลือกจากรายชื่อ --":
        current_user = selected_user

    if current_user != "":
        get_or_create_user(current_user)
        st.success(f"กำลังใช้งานในชื่อ: **{current_user}**")

        tab1, tab2, tab3, tab4 = st.tabs([
            "⭐ บันทึกดอกไม้ที่คุณชอบ",
            "📖 ประวัติดอกไม้ที่คุณเลือกไว้",
            "👥 ผู้ใช้ที่มีรสนิยมใกล้เคียง",
            "🎯 ดอกไม้แนะนำสำหรับคุณ",
        ])

        # --- TAB 1: บันทึกดอกไม้ที่ชอบ ---
        with tab1:
            st.subheader(f"เลือกระดับคะแนนความชอบดอกไม้สำหรับคุณ ({current_user})")
            df_flowers_all = get_all_flowers()
            if not df_flowers_all.empty:
                with st.form("rate_flower_form"):
                    selected_flower = st.selectbox("เลือกดอกไม้:", df_flowers_all["name"].tolist())
                    rating_given = st.slider("ให้คะแนนความชอบ (1 - 5 ดาว):", 1, 5, 5)
                    submit_rating = st.form_submit_button("บันทึกความชอบ")

                    if submit_rating:
                        add_user_preference(current_user, selected_flower, rating_given)
                        st.success(f"บันทึกความชอบ {selected_flower} ({rating_given} ดาว) เรียบร้อยแล้ว!")
                        st.rerun()
            else:
                st.warning("ยังไม่มีดอกไม้ในระบบ กรุณาติดต่อ Admin เพื่อกด Setup ข้อมูลเริ่มต้นก่อนครับ")

        # --- TAB 2: ดูประวัติที่ชอบ ---
        with tab2:
            st.subheader(f"รายการดอกไม้ที่ {current_user} บันทึกชอบไว้")
            df_user_fav = get_user_preferred_flowers(current_user)
            if not df_user_fav.empty:
                cols = st.columns(3)
                for idx, row in df_user_fav.iterrows():
                    with cols[idx % 3]:
                        with st.container(border=True):
                            if row.get("image_url"):
                                st.image(row["image_url"], use_container_width=True)
                            st.subheader(f"{row['flower']}")
                            st.write(f"**ความหมาย:** {row['meaning']}")
                            st.caption(f"⭐ คะแนนความชอบ: {row['rating']}/5")
            else:
                st.info("ยังไม่มีรายการดอกไม้ที่เลือกไว้ โปรดไปที่แท็บ '⭐ บันทึกดอกไม้ที่คุณชอบ' เพื่อเพิ่มดอกไม้ครับ")

        # --- TAB 3: ดูผู้ใช้ที่รสนิยมใกล้เคียง ---
        with tab3:
            st.subheader(f"ผู้ใช้คนอื่นที่มีรสนิยมใกล้เคียงกับ {current_user}")
            df_sim = get_similar_users(current_user)
            if not df_sim.empty:
                st.success(f"พบผู้ใช้คนอื่นในระบบที่ชอบดอกไม้ชนิดเดียวกันกับ {current_user}:")
                cols = st.columns(3)
                for idx, row in df_sim.iterrows():
                    with cols[idx % 3]:
                        with st.container(border=True):
                            if row.get("image_url"):
                                st.image(row["image_url"], use_container_width=True)
                            st.subheader(f"🤝 {row['similar_user']}")
                            st.write(f"🌸 ชอบเหมือนกัน: **{row['flower']}**")
                            st.write(f"*{row['meaning']}*")
                            st.caption(f"คะแนนที่ {row['similar_user']} ให้ไว้: {row['other_rating']}/5")
            else:
                st.info("ยังไม่พบผู้ใช้ที่มีรสนิยมใกล้เคียง (ลองไปที่แท็บแรก แล้วกดเลือกบันทึกดอกไม้ที่ชอบดูครับ)")

        # --- TAB 4: คำนวณดอกไม้แนะนำ ---
        with tab4:
            st.subheader(f"ดอกไม้แนะนำพิเศษคำนวณสำหรับ {current_user}")
            df_rec = recommend_flowers_for_user(current_user)
            if not df_rec.empty:
                cols = st.columns(3)
                for idx, row in df_rec.iterrows():
                    with cols[idx % 3]:
                        with st.container(border=True):
                            if row.get("image_url"):
                                st.image(row["image_url"], use_container_width=True)
                            st.subheader(f"{row['flower']}")
                            st.write(f"**ความหมาย:** {row['meaning']}")
            else:
                st.info("ไม่มีดอกไม้แนะนำเพิ่มเติมในขณะนี้")
    else:
        st.info("👆 โปรดเลือกรายชื่อจากดร็อปดาวน์ หรือพิมพ์ชื่อของคุณในช่องด้านบนก่อนเริ่มใช้งาน")

        st.divider()
        st.subheader("🎲 สุ่มดอกไม้แนะนำประจำวัน")
        if st.button("✨ กดเพื่อสุ่มดอกไม้!", type="primary"):
            flower = get_random_recommended_flower()
            if flower:
                col1, col2 = st.columns([1, 2])
                with col1:
                    if flower.get("image_url"):
                        st.image(flower["image_url"], caption=flower["name"], use_container_width=True)
                with col2:
                    st.header(f"🌺 {flower['name']}")
                    st.subheader("ความหมาย (Meaning):")
                    st.write(f"*{flower['meaning']}*")
            else:
                st.warning("ยังไม่มีดอกไม้ในระบบ กรุณาให้ Admin กด Setup ข้อมูลเริ่มต้นก่อนครับ")

# ------------------------------------------
# 2. ระบบผู้ดูแลระบบ (ADMIN SIDE)
# ------------------------------------------
elif menu == "เข้าสู่ระบบ Admin":
    st.title("🔒 เข้าสู่ระบบผู้ดูแลระบบ (Admin Access)")

    if "admin_logged_in" not in st.session_state:
        st.session_state["admin_logged_in"] = False

    if not st.session_state["admin_logged_in"]:
        with st.form("login_form"):
            admin_password = st.text_input("กรุณากรอกรหัสผ่าน Admin:", type="password")
            btn_login = st.form_submit_button("เข้าสู่ระบบ")

            if btn_login:
                if admin_password == ADMIN_PASSWORD:
                    st.session_state["admin_logged_in"] = True
                    st.success("เข้าสู่ระบบสำเร็จ!")
                    st.rerun()
                else:
                    st.error("รหัสผ่านไม่ถูกต้อง!")
    else:
        col_title, col_logout = st.columns([4, 1])
        with col_title:
            st.subheader("⚙️ เมนูจัดการข้อมูลหลังบ้าน")
        with col_logout:
            if st.button("ออกจากระบบ (Logout)"):
                st.session_state["admin_logged_in"] = False
                st.rerun()

        st.divider()

        admin_action = st.sidebar.selectbox(
            "การจัดการหลังบ้าน:",
            ["รายการดอกไม้ทั้งหมด", "เพิ่มดอกไม้ใหม่", "แก้ไข/ลบ ดอกไม้", "จัดการผู้ใช้ (Users)", "Setup ข้อมูลเริ่มต้น (Demo Data)"],
        )

        # --- 1. ดูรายการทั้งหมด ---
        if admin_action == "รายการดอกไม้ทั้งหมด":
            st.subheader("📋 รายการดอกไม้ในระบบ")
            df_flowers = get_all_flowers()
            st.dataframe(df_flowers, use_container_width=True)

        # --- 2. เพิ่มดอกไม้ ---
        elif admin_action == "เพิ่มดอกไม้ใหม่":
            st.subheader("➕ เพิ่มดอกไม้ใหม่เข้าสู่ระบบ")
            with st.form("add_flower_form"):
                name = st.text_input("ชื่อดอกไม้ (ภาษาอังกฤษ):")
                meaning = st.text_area("ความหมายของดอกไม้:")
                image_url = st.text_input("URL รูปภาพดอกไม้ (https://...):")
                submit = st.form_submit_button("บันทึกดอกไม้")

                if submit:
                    name_clean = name.strip()
                    meaning_clean = meaning.strip()
                    if name_clean and meaning_clean:
                        add_flower(name_clean, meaning_clean, image_url.strip())
                        st.success(f"เพิ่มดอกไม้ {name_clean} เรียบร้อยแล้ว!")
                        st.rerun()
                    else:
                        st.error("กรุณากรอกชื่อและความหมายให้ครบถ้วน")

        # --- 3. แก้ไข/ลบ ดอกไม้ ---
        elif admin_action == "แก้ไข/ลบ ดอกไม้":
            st.subheader("🛠️ แก้ไขหรือลบข้อมูลดอกไม้")
            df_flowers = get_all_flowers()
            if not df_flowers.empty:
                flower_list = df_flowers["name"].tolist()
                selected_flower_name = st.selectbox("เลือกดอกไม้ที่ต้องการจัดการ:", flower_list)
                selected_data = df_flowers[df_flowers["name"] == selected_flower_name].iloc[0]

                col1, col2 = st.columns(2)

                with col1:
                    st.write("### ✏️ แก้ไขข้อมูล")
                    with st.form("edit_flower_form"):
                        new_meaning = st.text_area("ความหมาย:", value=selected_data["meaning"])
                        new_image_url = st.text_input("URL รูปภาพ:", value=selected_data.get("image_url", "") or "")
                        btn_update = st.form_submit_button("อัปเดตข้อมูล")

                        if btn_update:
                            update_flower(selected_flower_name, new_meaning.strip(), new_image_url.strip())
                            st.success("อัปเดตข้อมูลสำเร็จ!")
                            st.rerun()

                with col2:
                    st.write("### 🗑️ ลบข้อมูล")
                    st.warning(f"ต้องการลบ {selected_flower_name} ออกจากระบบ?")
                    if st.button("ยืนยันการลบดอกไม้นี้", type="primary"):
                        delete_flower(selected_flower_name)
                        st.success(f"ลบ {selected_flower_name} เรียบร้อยแล้ว!")
                        st.rerun()
            else:
                st.info("ยังไม่มีดอกไม้ในระบบ")

        # --- 4. จัดการผู้ใช้ ---
        elif admin_action == "จัดการผู้ใช้ (Users)":
            st.subheader("👤 รายชื่อผู้ใช้ทั้งหมด")
            all_users = get_all_users()
            if all_users:
                st.dataframe(pd.DataFrame({"name": all_users}), use_container_width=True)
            else:
                st.info("ยังไม่มีผู้ใช้ในระบบ")

            st.divider()
            col_add, col_edit, col_del = st.columns(3)

            # --- เพิ่มผู้ใช้ใหม่ ---
            with col_add:
                st.write("### ➕ เพิ่มผู้ใช้ใหม่")
                with st.form("add_user_form", clear_on_submit=True):
                    new_user_name = st.text_input("ชื่อผู้ใช้ใหม่:")
                    submit_add_user = st.form_submit_button("บันทึกผู้ใช้")
                    if submit_add_user:
                        new_user_name_clean = new_user_name.strip()
                        if new_user_name_clean:
                            add_user(new_user_name_clean)
                            st.success(f"เพิ่มผู้ใช้ {new_user_name_clean} เรียบร้อยแล้ว!")
                            st.rerun()
                        else:
                            st.error("กรุณากรอกชื่อผู้ใช้")

            # --- แก้ไขชื่อผู้ใช้ ---
            with col_edit:
                st.write("### ✏️ แก้ไขชื่อผู้ใช้")
                if all_users:
                    with st.form("edit_user_form"):
                        user_to_edit = st.selectbox("เลือกผู้ใช้ที่จะแก้ไข:", all_users, key="edit_user_select")
                        new_name_for_user = st.text_input("ชื่อใหม่:")
                        submit_edit_user = st.form_submit_button("บันทึกชื่อใหม่")
                        if submit_edit_user:
                            new_name_clean = new_name_for_user.strip()
                            if not new_name_clean:
                                st.error("กรุณากรอกชื่อใหม่")
                            elif new_name_clean == user_to_edit:
                                st.warning("ชื่อใหม่เหมือนชื่อเดิม ไม่มีอะไรเปลี่ยนแปลง")
                            else:
                                try:
                                    rename_user(user_to_edit, new_name_clean)
                                    st.success(f"เปลี่ยนชื่อ {user_to_edit} เป็น {new_name_clean} เรียบร้อยแล้ว!")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"แก้ไขไม่สำเร็จ (อาจมีชื่อ '{new_name_clean}' อยู่แล้วในระบบ): {exc}")
                else:
                    st.caption("ยังไม่มีผู้ใช้ให้แก้ไข")

            # --- ลบผู้ใช้ ---
            with col_del:
                st.write("### 🗑️ ลบผู้ใช้")
                if all_users:
                    del_user = st.selectbox("เลือกผู้ใช้ที่จะลบ:", all_users, key="del_user_select")
                    st.caption("จะลบความชอบ (PREFERS) ทั้งหมดของผู้ใช้นี้ไปด้วย")
                    if st.button("ยืนยันลบผู้ใช้นี้", type="primary"):
                        delete_user(del_user)
                        st.success(f"ลบผู้ใช้ {del_user} เรียบร้อยแล้ว!")
                        st.rerun()
                else:
                    st.caption("ยังไม่มีผู้ใช้ให้ลบ")

        # --- 5. Setup ข้อมูลเริ่มต้น ---
        elif admin_action == "Setup ข้อมูลเริ่มต้น (Demo Data)":
            st.subheader("🚀 ตั้งค่าและโหลดข้อมูลเริ่มต้น")
            st.write("กดปุ่มด้านล่างเพื่อสร้าง Constraints และโหลดชุดข้อมูล Demo (10 Users / 13 Flowers) เข้า Neo4j")
            st.caption("ปลอดภัยต่อการกดซ้ำ — ใช้ MERGE ทั้งหมด จึงไม่สร้างข้อมูลซ้ำซ้อน")
            if st.button("เริ่มสร้างข้อมูล Demo Data"):
                with st.spinner("กำลังบันทึกข้อมูลลง Neo4j AuraDB..."):
                    seed_demo_data()
                st.success("ลงข้อมูลเริ่มต้นเรียบร้อยแล้ว!")
