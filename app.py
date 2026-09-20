import streamlit as st
import sqlite3
import os
import io
import re
import urllib.request
import urllib.parse
import unicodedata
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

# Safe imports for optional third-party packages
try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    from pdfminer.high_level import extract_text as pdfminer_extract
    HAS_PDFMINER = True
except ImportError:
    HAS_PDFMINER = False

try:
    import docx
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if os.path.exists(FONT_PATH):
        pdfmetrics.registerFont(TTFont('DejaVuSans', FONT_PATH))
        REPORTLAB_FONT = 'DejaVuSans'
    else:
        REPORTLAB_FONT = 'Helvetica'
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

DB_NAME = "geography_exam.db"

st.set_page_config(
    page_title="WBBSE Geography Learning & Exam Portal",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

def get_connection():
    try:
        os.makedirs(os.path.dirname(DB_NAME), exist_ok=True)
    except Exception:
        pass
    return sqlite3.connect(DB_NAME, timeout=30)

# Advanced Bengali Text Normalization (Python 3.12+ safe)
def normalize_bengali_text(text):
    if not text:
        return ""
    text = unicodedata.normalize('NFC', text)
    text = re.sub(r'\u09C7([\u0985-\u09B9](\u09CD[\u0985-\u09B9])?)', lambda m: m.group(1) + '\u09C7', text)
    text = re.sub(r'\u09C8([\u0985-\u09B9](\u09CD[\u0985-\u09B9])?)', lambda m: m.group(1) + '\u09C8', text)
    text = re.sub(r'[\u200B\u200C\u200D]', '', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()

def extract_text_from_pdf_file(file_obj):
    extracted = ""
    if HAS_PDFPLUMBER:
        try:
            file_obj.seek(0)
            with pdfplumber.open(file_obj) as pdf:
                for page in pdf.pages:
                    p_txt = page.extract_text(layout=True) or page.extract_text()
                    if p_txt:
                        extracted += p_txt + "\n"
        except Exception:
            pass
    if not extracted.strip() and HAS_PYPDF:
        try:
            file_obj.seek(0)
            reader = pypdf.PdfReader(file_obj)
            for page in reader.pages:
                p_txt = page.extract_text()
                if p_txt:
                    extracted += p_txt + "\n"
        except Exception:
            pass
    if not extracted.strip() and HAS_PDFMINER:
        try:
            file_obj.seek(0)
            extracted = pdfminer_extract(file_obj)
        except Exception:
            pass
    return normalize_bengali_text(extracted)

# ============================================================================
# DATABASE MIGRATION — All tables + Default chapters
# ============================================================================
def verify_and_migrate_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""CREATE TABLE IF NOT EXISTS exams (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, description TEXT)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS topics (
        id INTEGER PRIMARY KEY AUTOINCREMENT, exam_id INTEGER, name TEXT,
        FOREIGN KEY(exam_id) REFERENCES exams(id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, topic_id INTEGER,
        pyq_year TEXT DEFAULT '', is_pyq INTEGER DEFAULT 0,
        question_text TEXT, question_text_en TEXT,
        option_a TEXT, option_a_en TEXT, option_b TEXT, option_b_en TEXT,
        option_c TEXT, option_c_en TEXT, option_d TEXT, option_d_en TEXT,
        correct_option CHAR(1), explanation TEXT, explanation_en TEXT,
        difficulty TEXT DEFAULT 'Medium', is_descriptive INTEGER DEFAULT 0,
        marks INTEGER DEFAULT 1, model_answer TEXT, model_answer_en TEXT,
        marking_scheme TEXT, marking_scheme_en TEXT,
        FOREIGN KEY(topic_id) REFERENCES topics(id))""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE,
        password TEXT, role TEXT DEFAULT 'student', full_name TEXT,
        school_name TEXT, class_grade TEXT, phone TEXT, district TEXT,
        approved INTEGER DEFAULT 0, is_admin INTEGER DEFAULT 0,
        referral_code TEXT DEFAULT '', referral_count INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS student_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_name TEXT,
        student_phone TEXT, school_name TEXT, district TEXT, exam_name TEXT,
        topic_name TEXT, score INTEGER, total_questions INTEGER,
        percentage REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS student_doubts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_username TEXT,
        student_name TEXT, question_id INTEGER,
        assigned_teacher_username TEXT DEFAULT '',
        teacher_answer TEXT DEFAULT '', status TEXT DEFAULT 'Pending',
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS mock_tests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, test_type TEXT, code_num TEXT,
        file_name TEXT, file_data BLOB, uploader TEXT, price INTEGER DEFAULT 0,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS system_settings (
        key TEXT PRIMARY KEY, value TEXT)""")
    
    # PHASE 1: Duplicate log & Ask Corner
    cursor.execute("""CREATE TABLE IF NOT EXISTS duplicate_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, original_q_id INTEGER,
        duplicate_q_id INTEGER, similarity REAL, removed_by TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS ask_corner (
        id INTEGER PRIMARY KEY AUTOINCREMENT, submitter_username TEXT,
        submitter_name TEXT, submitter_role TEXT, category TEXT,
        message TEXT, admin_reply TEXT DEFAULT '',
        status TEXT DEFAULT 'New',
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    
    # PHASE 2: Payments & Purchases
    cursor.execute("""CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, user_name TEXT,
        user_role TEXT, phone TEXT, item_type TEXT, item_id TEXT,
        amount INTEGER, upi_ref TEXT,
        status TEXT DEFAULT 'Pending Verification',
        admin_note TEXT DEFAULT '',
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        approved_at DATETIME)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS user_purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, item_type TEXT,
        item_id TEXT, payment_id INTEGER, status TEXT DEFAULT 'Active',
        activated_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    
    # PHASE 3: Exam Submissions
    cursor.execute("""CREATE TABLE IF NOT EXISTS exam_submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_username TEXT,
        student_name TEXT, exam_type TEXT, exam_code TEXT,
        answer_file_name TEXT, answer_file_data BLOB,
        submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        checker_username TEXT DEFAULT '', status TEXT DEFAULT 'Submitted',
        corrected_file_name TEXT DEFAULT '', corrected_file_data BLOB,
        corrected_at DATETIME, admin_note TEXT DEFAULT '')""")
    
    cursor.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('portal_url', 'https://geography-exam-app.streamlit.app')")
    cursor.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('upi_id', 'shawonkar6466-1@oksbi')")
    
    # Default exam + 6 chapters
    cursor.execute("INSERT OR IGNORE INTO exams (id, name, description) VALUES (1, 'Madhyamik Class 10', 'WBBSE Class 10 Geography & Environment')")
    cursor.execute("SELECT COUNT(*) FROM topics")
    if cursor.fetchone()[0] == 0:
        default_topics = [
            "১. বহির্জাত প্রক্রিয়া ও তাদের দ্বারা সৃষ্ট ভূমিরূপ / Exogenic Processes and Created Landforms",
            "২. বায়ুমণ্ডল / Atmosphere",
            "৩. বারিমণ্ডল / Hydrosphere",
            "৪. বর্জ্য ব্যবস্থাপনা / Waste Management",
            "৫. ভারত / India",
            "৬. উপগ্রহ চিত্র ও ভূ-বৈচিত্র্যসূচক মানচিত্র / Satellite Imagery and Topographical Maps"
        ]
        for t_name in default_topics:
            cursor.execute("INSERT INTO topics (exam_id, name) VALUES (1, ?)", (t_name,))

    conn.commit()
    conn.close()

verify_and_migrate_db()

ADMIN_PASSCODE = "Shawon2026@123SUKANNYA"

# ============================================================================
# CSS
# ============================================================================
st.markdown("""
    <style>
    .main { background-color: #f1f5f9 !important; color: #0f172a !important; }
    .stApp { font-family: 'SolaimanLipi', 'Kalpurush', 'Noto Sans Bengali', 'Segoe UI', Arial, sans-serif !important; }
    .stTextInput input, .stTextArea textarea, .stSelectbox select {
        background-color: #ffffff !important; color: #0f172a !important;
        border: 1.5px solid #475569 !important; border-radius: 8px !important; font-weight: 600 !important; }
    .header-box { background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 50%, #0284c7 100%);
        padding: 28px; border-radius: 16px; color: #ffffff !important; text-align: center;
        margin-bottom: 25px; box-shadow: 0 10px 25px rgba(0,0,0,0.15); }
    .header-box h1 { color: #ffffff !important; font-size: 2.1rem !important; font-weight: 700 !important; }
    .card-short { background-color: #ffffff !important; color: #000000 !important; padding: 22px;
        border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); border-left: 6px solid #2563eb;
        margin-bottom: 18px; border-top: 1.5px solid #cbd5e1; border-right: 1.5px solid #cbd5e1;
        border-bottom: 1.5px solid #cbd5e1; }
    .card-short h4, .card-broad h4 { color: #000000 !important; font-weight: 900 !important; font-size: 1.15rem !important; }
    .card-broad { background-color: #ffffff !important; color: #000000 !important; padding: 22px;
        border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); border-left: 6px solid #7c3aed;
        margin-bottom: 18px; border-top: 1.5px solid #cbd5e1; border-right: 1.5px solid #cbd5e1;
        border-bottom: 1.5px solid #cbd5e1; }
    .price-card { background: linear-gradient(135deg, #ffffff 0%, #eff6ff 100%);
        padding: 22px; border-radius: 14px; text-align: center;
        border: 2px solid #2563eb; margin-bottom: 15px;
        box-shadow: 0 6px 18px rgba(37,99,235,0.12); }
    .price-card h3 { color: #1e3a8a !important; margin: 0 0 8px 0; font-size: 1.3rem !important; }
    .price-tag { font-size: 2.2rem; font-weight: 900; color: #059669; margin: 10px 0; }
    .footer-block { background-color: #0f172a; color: #f8fafc; padding: 28px;
        border-radius: 14px; text-align: center; margin-top: 50px;
        border-top: 5px solid #2563eb; box-shadow: 0 10px 20px rgba(0,0,0,0.2); }
    .lock-box { background: #fef3c7; border: 2px dashed #f59e0b; padding: 20px;
        border-radius: 12px; text-align: center; margin-bottom: 15px; }
    .ask-corner-card { background: #ffffff; padding: 15px; border-radius: 10px;
        border-left: 5px solid #16a34a; margin-bottom: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
    </style>
""", unsafe_allow_html=True)

# ============================================================================
# Helpers
# ============================================================================
GEO_TRANS_DICT = {
    "বহির্জাত প্রক্রিয়া": "Exogenic Processes", "ভূমিরূপ": "Landforms",
    "বায়ুমণ্ডল": "Atmosphere", "বারিমণ্ডল": "Hydrosphere",
    "বর্জ্য ব্যবস্থাপনা": "Waste Management", "ভারত": "India",
    "উপগ্রহ চিত্র": "Satellite Imagery", "ভূ-বৈচিত্র্যসূচক মানচিত্র": "Topographical Maps",
    "পর্যায়ন": "Gradation", "বদ্বীপ": "Delta", "জলপ্রপাত": "Waterfall",
    "ক্যানিয়ন": "Canyon", "মন্থকূপ": "Pot hole"
}

def translate_geo_term(text, target_lang):
    if not text:
        return ""
    if target_lang == "English":
        res = text
        for bn, en in GEO_TRANS_DICT.items():
            res = res.replace(bn, en)
        return res
    return text

def parse_and_categorize_questions(content_text):
    candidates = []
    lines = [line.strip() for line in content_text.split('\n') if line.strip()]
    current_q = None
    for line in lines:
        match_q = re.match(r'^(Q?\d+[\.\)]|\d+\.\d+|প্রঃ?\d+[\.\)])\s*(.*)', line, re.IGNORECASE)
        if match_q:
            if current_q:
                candidates.append(current_q)
            q_txt = match_q.group(2) if match_q.group(2) else line
            m_val = 1
            if re.search(r'([২2]\s*নম্বর|2\s*marks?|[২2]\s*মার্কেল|মান\s*[:\-]?\s*[২2])', line, re.IGNORECASE):
                m_val = 2
            elif re.search(r'([৩3]\s*নম্বর|3\s*marks?|[৩3]\s*মার্কেল|মান\s*[:\-]?\s*[৩3])', line, re.IGNORECASE):
                m_val = 3
            elif re.search(r'([৫5]\s*নম্বর|5\s*marks?|[৫5]\s*মার্কেল|মান\s*[:\-]?\s*[৫5])', line, re.IGNORECASE):
                m_val = 5
            current_q = {
                "question": normalize_bengali_text(q_txt), "marks": m_val,
                "opt_a": "", "opt_b": "", "opt_c": "", "opt_d": "",
                "correct": "A", "explanation": "Extracted from uploaded document.",
                "is_descriptive": 1 if m_val > 1 else 0
            }
        elif current_q:
            if re.search(r'^\(ক\)|^A\)|^a\)', line):
                current_q["opt_a"] = normalize_bengali_text(line)
            elif re.search(r'^\(খ\)|^B\)|^b\)', line):
                current_q["opt_b"] = normalize_bengali_text(line)
            elif re.search(r'^\(গ\)|^C\)|^c\)', line):
                current_q["opt_c"] = normalize_bengali_text(line)
            elif re.search(r'^\(ঘ\)|^D\)|^d\)', line):
                current_q["opt_d"] = normalize_bengali_text(line)
            else:
                current_q["question"] += " " + normalize_bengali_text(line)
    if current_q:
        candidates.append(current_q)
    return candidates

def check_duplicate_question(new_q_text, topic_id, threshold=0.75):
    import difflib
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, question_text, topic_id FROM questions WHERE topic_id = ?", (topic_id,))
    existing_qs = cursor.fetchall()
    conn.close()
    candidate_norm = re.sub(r'[^\w\s]', '', normalize_bengali_text(new_q_text)).lower()
    best_match = None
    highest_ratio = 0.0
    for q_id, q_text, t_id in existing_qs:
        q_norm = re.sub(r'[^\w\s]', '', normalize_bengali_text(q_text)).lower()
        ratio = difflib.SequenceMatcher(None, candidate_norm, q_norm).ratio()
        if ratio > highest_ratio:
            highest_ratio = ratio
            best_match = (q_id, q_text, t_id)
    if highest_ratio >= threshold:
        return best_match, highest_ratio
    return None, highest_ratio

def user_has_purchase(username, item_type, item_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM user_purchases
        WHERE username = ? AND item_type = ? AND item_id = ? AND status = 'Active'
    """, (username, item_type, str(item_id)))
    cnt = cursor.fetchone()[0]
    conn.close()
    return cnt > 0

def get_portal_url():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM system_settings WHERE key = 'portal_url'")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else "https://geography-exam-app.streamlit.app"

def get_upi_id():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM system_settings WHERE key = 'upi_id'")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else "shawonkar6466-1@oksbi"

# ============================================================================
# Session State
# ============================================================================
defaults = {
    'logged_in': False, 'username': "", 'role': "student",
    'full_name': "", 'school_name': "", 'phone': "", 'district': "",
    'language': "Bengali", 'admin_view_mode': "Admin Control Panel",
    'referred_by': ""
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Auto read ?ref=CODE
try:
    query_ref = st.query_params.get("ref", "")
    if query_ref:
        st.session_state.referred_by = query_ref
except Exception:
    pass

# ============================================================================
# Sidebar
# ============================================================================
st.sidebar.markdown("<h1 style='text-align:center;'>🌍</h1>", unsafe_allow_html=True)
st.sidebar.title("🌍 WBBSE Geo Lab Portal")
st.session_state.language = st.sidebar.radio("🌐 Language / ভাষা", ["Bengali", "English"])
lang = st.session_state.language

# Banner
if lang == "Bengali":
    st.markdown("""
        <div class="header-box">
            <h1>🌍 পশ্চিমবঙ্গ ভূগোল পরীক্ষা প্রস্তুতি ও ডিজিটাল ল্যাব</h1>
            <p>ওয়েস্ট বেঙ্গল বোর্ড (WBBSE) দশম শ্রেণী অফিসিয়াল ভূগোল সিলেবাস প্র্যাকটিস হাব</p>
        </div>""", unsafe_allow_html=True)
else:
    st.markdown("""
        <div class="header-box">
            <h1>🌍 West Bengal Board Geography Portal & Geo Lab</h1>
            <p>Dedicated Practice Platform for WBBSE Class 10 Geography & Environment Syllabus</p>
        </div>""", unsafe_allow_html=True)

# ============================================================================
# LOGIN / REGISTRATION
# ============================================================================
if not st.session_state.logged_in:
    tab_login, tab_student_reg, tab_teacher_reg = st.tabs([
        "🔑 Login / লগইন",
        "🎓 Student Register",
        "👨‍🏫 Teacher Register"
    ])
    
    with tab_login:
        st.subheader("Sign in to your Account")
        role_select = st.radio("Select Role:", ["Student", "Teacher", "Admin"], horizontal=True)
        login_user = st.text_input("Phone Number or Username", key="login_u")
        login_pass = st.text_input("Password", type="password", key="login_p")
        if st.button("Enter Portal", use_container_width=True):
            if role_select == "Admin" and login_user == "admin" and login_pass == ADMIN_PASSCODE:
                st.session_state.logged_in = True
                st.session_state.username = "admin"
                st.session_state.role = "admin"
                st.session_state.full_name = "Shawon Kar (Head Admin)"
                st.rerun()
            else:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""SELECT password, role, full_name, school_name, phone, district, approved 
                    FROM users WHERE (username = ? OR phone = ?)""", (login_user, login_user))
                row = cursor.fetchone()
                conn.close()
                if row:
                    db_pass, db_role, f_name, sch, ph, dist, approved = row
                    if db_pass == login_pass:
                        if approved == 1:
                            st.session_state.logged_in = True
                            st.session_state.username = login_user
                            st.session_state.role = db_role
                            st.session_state.full_name = f_name
                            st.session_state.school_name = sch
                            st.session_state.phone = ph
                            st.session_state.district = dist
                            st.rerun()
                        else:
                            st.warning("⚠️ আপনার account এখনো Admin approval এর অপেক্ষায় আছে।")
                    else:
                        st.error("❌ Incorrect Password.")
                else:
                    st.error("❌ Account not found.")
    
    with tab_student_reg:
        st.subheader("New Student Registration")
        col1, col2 = st.columns(2)
        s_name = col1.text_input("Student Name", key="s_name")
        s_school = col2.text_input("School Name", key="s_sch")
        s_class = col1.selectbox("Class", ["Class 10 (Madhyamik)"])
        s_phone = col2.text_input("Phone Number", key="s_ph")
        s_dist = col1.text_input("District", key="s_dist")
        s_pass = col2.text_input("Set Password", type="password", key="s_pass")
        ref_default = st.session_state.get('referred_by', '')
        if ref_default:
            st.success(f"🎁 Referral Code Auto-Detected: `{ref_default}`")
        ref_input = st.text_input("Referral Code (Optional)", value=ref_default, key="s_ref")
        if st.button("Submit Student Registration", use_container_width=True):
            if s_name and s_school and s_phone and s_pass:
                try:
                    conn = get_connection()
                    cursor = conn.cursor()
                    auto_ref = f"GEO-REF-{s_phone[-4:] if len(s_phone)>=4 else '10'}"
                    cursor.execute("""INSERT INTO users (username, password, role, full_name, school_name, class_grade, phone, district, approved, is_admin, referral_code)
                        VALUES (?, ?, 'student', ?, ?, ?, ?, ?, 0, 0, ?)""",
                        (s_phone, s_pass, s_name, s_school, s_class, s_phone, s_dist, auto_ref))
                    if ref_input.strip():
                        cursor.execute("UPDATE users SET referral_count = referral_count + 1 WHERE referral_code = ?", (ref_input.strip(),))
                    conn.commit()
                    conn.close()
                    st.success("🎉 Registration requested! Shawon Sir approve করলেই login করতে পারবেন।")
                except sqlite3.IntegrityError:
                    st.error("❌ এই phone number দিয়ে account আছে।")
            else:
                st.error("⚠️ সব required field পূরণ করুন।")
    
    with tab_teacher_reg:
        st.subheader("New Teacher Registration")
        col1, col2 = st.columns(2)
        t_name = col1.text_input("Teacher Name", key="t_name")
        t_school = col2.text_input("School Name", key="t_sch")
        t_phone = col1.text_input("Phone Number", key="t_ph")
        t_dist = col2.text_input("District", key="t_dist")
        t_pass = col1.text_input("Set Password", type="password", key="t_pass")
        t_ref_default = st.session_state.get('referred_by', '')
        if t_ref_default:
            st.success(f"🎁 Referral Code Auto-Detected: `{t_ref_default}`")
        t_ref_in = st.text_input("Referral Code (Optional)", value=t_ref_default, key="t_ref")
        if st.button("Submit Teacher Registration", use_container_width=True):
            if t_name and t_school and t_phone and t_pass:
                try:
                    conn = get_connection()
                    cursor = conn.cursor()
                    auto_t_ref = f"GEO-REF-T{t_phone[-4:] if len(t_phone)>=4 else '99'}"
                    cursor.execute("""INSERT INTO users (username, password, role, full_name, school_name, class_grade, phone, district, approved, is_admin, referral_code)
                        VALUES (?, ?, 'teacher', ?, ?, 'Faculty', ?, ?, 0, 0, ?)""",
                        (t_phone, t_pass, t_name, t_school, t_phone, t_dist, auto_t_ref))
                    if t_ref_in.strip():
                        cursor.execute("UPDATE users SET referral_count = referral_count + 1 WHERE referral_code = ?", (t_ref_in.strip(),))
                    conn.commit()
                    conn.close()
                    st.success("🎉 Teacher registration requested! Admin approval এর অপেক্ষা করুন।")
                except sqlite3.IntegrityError:
                    st.error("❌ এই phone number দিয়ে account আছে।")
            else:
                st.error("⚠️ সব required field পূরণ করুন।")

else:
    # ========================================================================
    # LOGGED-IN INTERFACE
    # ========================================================================
    st.sidebar.markdown(f"👤 **Name:** `{st.session_state.full_name}`")
    st.sidebar.markdown(f"🎭 **Role:** `{st.session_state.role.capitalize()}`")
    if st.session_state.school_name:
        st.sidebar.caption(f"🏫 {st.session_state.school_name} | {st.session_state.district}")
    
    if st.session_state.role == "admin":
        st.sidebar.markdown("---")
        st.sidebar.markdown("👑 **Admin Super-Control**")
        st.session_state.admin_view_mode = st.sidebar.radio("View Portal As:", ["Admin Control Panel", "Teacher View", "Student View"])
    
    if st.sidebar.button("Logout"):
        for k in ['logged_in', 'username', 'role', 'full_name', 'school_name', 'phone', 'district', 'referred_by']:
            st.session_state[k] = defaults.get(k, "")
        st.rerun()
    
    role = st.session_state.role
    if role == "admin":
        if st.session_state.admin_view_mode == "Teacher View":
            active_view_role = "teacher"
        elif st.session_state.admin_view_mode == "Student View":
            active_view_role = "student"
        else:
            active_view_role = "admin"
    else:
        active_view_role = role
    
    # Navigation menus
    if active_view_role == "student":
        st_nav = st.sidebar.selectbox("🎯 Navigation Menu", [
            "📖 Practice Center",
            "❓ My Help / Doubt Requests",
            "📄 Mock Tests & Suggestions",
            "📝 My Exam Submissions",
            "📁 Madhyamik Drive Papers",
            "🎁 Share & Referral Links",
            "💡 Ask Corner (Suggestions)",
            "💳 Pricing & Payment"
        ])
    elif active_view_role == "teacher":
        st_nav = st.sidebar.selectbox("🎯 Navigation Menu", [
            "📥 Assigned Student Doubts",
            "📖 Question Bank Manager",
            "📄 Upload Mock Tests & Suggestions",
            "📝 Check Student Answer Sheets",
            "👨‍🏫 Student Track Records",
            "📁 Madhyamik Drive Papers",
            "🎁 Share & Referral Links",
            "💡 Ask Corner (Suggestions)",
            "💳 Pricing & Payment"
        ])
    else:
        st_nav = st.sidebar.selectbox("🎯 Navigation Menu", [
            "🛡️ User Approvals",
            "❓ Student Doubt Assignment Hub",
            "📖 Question Bank Manager",
            "📄 Upload Mock Tests & Suggestions",
            "💡 Ask Corner Suggestions",
            "💳 Payment Verifications",
            "📝 Exam Answer Sheet Checking",
            "📁 Madhyamik Drive Papers",
            "📊 Analytics & Track Records",
            "🎁 Share & Referral Links"
        ])
    
    # ========================================================================
    # SHARED: Madhyamik Drive Papers
    # ========================================================================
    if st_nav == "📁 Madhyamik Drive Papers":
        st.subheader("📁 Official Madhyamik Google Drive Papers")
        st.markdown("""
            <div style="background-color: #eff6ff; border: 2px solid #2563eb; padding: 22px; border-radius: 12px; margin-bottom: 20px;">
                <h3 style="color: #1e3a8a; margin-top:0;">📥 Official Madhyamik Board Question Papers</h3>
                <p>২০১৭ থেকে ২০২৬ সালের সব অফিশিয়াল মাধ্যমিক ভূগোল প্রশ্নপত্র:</p>
                <a href="https://drive.google.com/drive/folders/1q4cLE5sYcjElqSnZPQ4Tx4lkbrB-U-pj?usp=drive_link" target="_blank" style="background-color: #2563eb; color: white; padding: 10px 20px; border-radius: 8px; text-decoration: none; font-weight: bold; display: inline-block;">🔗 Open Google Drive Folder</a>
            </div>""", unsafe_allow_html=True)
        st.markdown("""
        ### 📋 Instructions:
        ১. উপরের বোতামে ক্লিক করলে Drive folder খুলবে।
        ২. প্রশ্নপত্র দেখতে ও ডাউনলোড করতে পারবেন।
        ৩. সব ফাইল অফিসিয়াল বোর্ড collection।
        """)
    
    # ========================================================================
    # SHARED: Share & Referral Links
    # ========================================================================
    elif st_nav == "🎁 Share & Referral Links":
        st.subheader("🎁 Refer Friends & Share Portal")
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT referral_code, referral_count FROM users WHERE username = ?", (st.session_state.username,))
        ref_row = cursor.fetchone()
        current_portal_url = get_portal_url()
        my_code = ref_row[0] if ref_row and ref_row[0] else "GEO-REF-10"
        my_count = ref_row[1] if ref_row and ref_row[1] else 0
        
        if role == "admin":
            st.markdown("#### 🌐 Portal URL Configuration")
            new_url_val = st.text_input("Official Web Link:", value=current_portal_url)
            if st.button("💾 Save Portal URL"):
                cursor.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('portal_url', ?)", (new_url_val.strip(),))
                conn.commit()
                current_portal_url = new_url_val.strip()
                st.success("✅ Updated!")
                st.rerun()
        conn.close()
        
        col1, col2 = st.columns(2)
        col1.metric("Your Referral Code", my_code)
        col2.metric("Successful Referrals", f"{my_count} / 100")
        st.progress(min(my_count / 100.0, 1.0))
        if my_count >= 100:
            st.balloons()
            st.success("🎉 CONGRATULATIONS! 100 referrals complete! Award Certificate Unlocked!")
        else:
            st.info(f"💡 {100 - my_count} more referrals needed for Certificate!")
        
        st.markdown("### 📲 Direct Share Links:")
        ref_link = f"{current_portal_url}?ref={my_code}"
        share_msg = f"🌍 Join WBBSE Class 10 Geography Portal!\n\n📚 Practice Sets, PYQs, Mock Tests & Doubt Solving\n\n👉 Click here: {ref_link}\n\n🔑 Your referral code: {my_code}\n\n(Use my code during signup!)"
        encoded_msg = urllib.parse.quote(share_msg)
        
        col_wa, col_sms, col_fb = st.columns(3)
        col_wa.markdown(f'<a href="https://api.whatsapp.com/send?text={encoded_msg}" target="_blank" style="background-color:#22c55e; color:white; padding:10px 16px; border-radius:8px; text-decoration:none; font-weight:bold; display:block; text-align:center;">📱 WhatsApp</a>', unsafe_allow_html=True)
        col_sms.markdown(f'<a href="sms:?body={encoded_msg}" style="background-color:#0284c7; color:white; padding:10px 16px; border-radius:8px; text-decoration:none; font-weight:bold; display:block; text-align:center;">💬 SMS</a>', unsafe_allow_html=True)
        col_fb.markdown(f'<a href="https://www.facebook.com/sharer/sharer.php?u={urllib.parse.quote(ref_link)}&quote={encoded_msg}" target="_blank" style="background-color:#1d4ed8; color:white; padding:10px 16px; border-radius:8px; text-decoration:none; font-weight:bold; display:block; text-align:center;">📘 Facebook</a>', unsafe_allow_html=True)
        
        st.markdown("#### 📋 Copy Share Text:")
        st.text_area("Share Text:", value=share_msg, height=140)
    
    # ========================================================================
    # SHARED: Ask Corner (Student + Teacher)
    # ========================================================================
    elif st_nav == "💡 Ask Corner (Suggestions)":
        st.subheader("💡 Ask Corner — Share Your Ideas!")
        st.markdown("""
            <div style="background-color:#eff6ff; border-left:5px solid #2563eb; padding:18px; border-radius:10px;">
            <h4>💬 Help Us Improve!</h4>
            <p>আপনার suggestion, idea, বা কোনো problem সরাসরি Admin এর কাছে পাঠান। Head Admin Shawon Sir নিজে দেখে reply দেবেন।</p>
            </div>""", unsafe_allow_html=True)
        
        with st.form("ask_corner_form"):
            ask_cat = st.selectbox("Category:", [
                "💡 নতুন Feature Idea", "🐛 Bug / সমস্যা",
                "📚 Question Bank Improve", "🎨 Design / UI Improvement",
                "💰 Pricing Related", "🎯 Suggestion / Feedback", "❓ অন্যান্য"
            ])
            ask_msg = st.text_area("আপনার Message:", height=180)
            ask_submitted = st.form_submit_button("📤 Submit to Admin", use_container_width=True)
            if ask_submitted:
                if ask_msg.strip():
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute("""INSERT INTO ask_corner (submitter_username, submitter_name, submitter_role, category, message)
                        VALUES (?, ?, ?, ?, ?)""",
                        (st.session_state.username, st.session_state.full_name, st.session_state.role, ask_cat, ask_msg.strip()))
                    conn.commit()
                    conn.close()
                    st.success("🎉 আপনার Message Admin এর কাছে পৌঁছে গেছে!")
                    st.balloons()
                else:
                    st.warning("⚠️ Message লিখুন।")
        
        st.markdown("---")
        st.markdown("### 📬 আপনার Previous Messages")
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""SELECT id, category, message, admin_reply, status, timestamp 
            FROM ask_corner WHERE submitter_username = ? ORDER BY id DESC LIMIT 20""",
            (st.session_state.username,))
        my_msgs = cursor.fetchall()
        conn.close()
        if not my_msgs:
            st.info("এখনো কোনো message পাঠাননি।")
        else:
            for m_id, cat, msg, rep, stat, ts in my_msgs:
                with st.expander(f"📌 #{m_id} — {cat} [{stat}] — {ts}"):
                    st.markdown(f"**Message:** {msg}")
                    if rep and rep.strip():
                        st.success(f"**Admin Reply:** {rep}")
                    else:
                        st.info("⏳ Admin এখনো reply দেননি।")
    
    # ========================================================================
    # SHARED: Pricing & Payment (Student + Teacher)
    # ========================================================================
    elif st_nav == "💳 Pricing & Payment":
        st.subheader("💳 Pricing Plans & Payment")
        st.markdown("""
            <div style="background:linear-gradient(135deg, #dbeafe 0%, #eff6ff 100%); padding:22px; border-radius:14px; margin-bottom:22px; border:2px solid #2563eb;">
            <h3 style="color:#1e3a8a; margin:0;">💰 Simple & Affordable Pricing</h3>
            <p>নিচের package এর যেকোনোটা কিনে Exam/Test unlock করুন। Payment সম্পূর্ণ UPI দিয়ে।</p>
            </div>""", unsafe_allow_html=True)
        
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("""<div class="price-card">
                <h3>📄 Chapter Exam Set</h3>
                <div class="price-tag">₹19</div>
                <p>প্রতি Set</p>
                <p style="font-size:0.9em; color:#475569;">Chapter Wise Examination</p>
            </div>""", unsafe_allow_html=True)
        with c2:
            st.markdown("""<div class="price-card">
                <h3>🎯 Final Mock Test</h3>
                <div class="price-tag">₹49</div>
                <p>প্রতি Set</p>
                <p style="font-size:0.9em; color:#475569;">Complete Final Mock Exam</p>
            </div>""", unsafe_allow_html=True)
        with c3:
            st.markdown("""<div class="price-card">
                <h3>💡 Board Suggestions</h3>
                <div class="price-tag">₹69</div>
                <p>প্রতি Set</p>
                <p style="font-size:0.9em; color:#475569;">Full Board Suggestions</p>
            </div>""", unsafe_allow_html=True)
        
        st.markdown("---")
        st.markdown("### 💳 Payment করবেন যেভাবে")
        
        upi_id = get_upi_id()
        col_qr, col_info = st.columns([1, 1])
        with col_qr:
            st.markdown("#### 📱 Scan & Pay (UPI)")
            try:
                st.image("payment_qr.png", width=280, caption="Shawon Kar UPI QR")
            except Exception:
                st.warning("⚠️ payment_qr.png পাওয়া যায়নি। Admin কে জানান।")
            st.markdown(f"**UPI ID:** `{upi_id}`")
        
        with col_info:
            st.markdown("#### 📋 Steps:")
            st.markdown("""
            ১. আপনার bKash/PhonePe/GPay/Paytm app খুলুন
            ২. QR scan করুন বা UPI ID paste করুন
            ৩. নির্দিষ্ট amount পাঠান (₹19 / ₹49 / ₹69)
            ৪. নিচের form এ **UPI Transaction ID** submit করুন
            ৫. Admin verification এর পর item unlock হবে
            """)
        
        st.markdown("---")
        st.markdown("### 📝 Payment Record Submit করুন")
        
        # Load available items
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, test_type, code_num, price FROM mock_tests ORDER BY id DESC")
        available_items = cursor.fetchall()
        conn.close()
        
        if not available_items:
            st.info("📭 এখনো কোনো Mock Test/Suggestion Admin upload করেনি।")
        else:
            item_options = {f"[{m[1]}] {m[2]} — ₹{m[3] or 0}": (m[0], m[1], m[3] or 0) for m in available_items}
            sel_item_label = st.selectbox("কোন Item unlock করতে চান?", ["-- Select --"] + list(item_options.keys()), key="pay_item_sel")
            
            upi_ref_in = st.text_input("UPI Transaction ID / Reference Number:", key="pay_upi_ref")
            
            if st.button("📤 Submit Payment for Verification", use_container_width=True, key="pay_submit"):
                if sel_item_label == "-- Select --" or not upi_ref_in.strip():
                    st.warning("⚠️ Item select করুন এবং UPI Ref Number দিন।")
                else:
                    m_id, m_type, m_price = item_options[sel_item_label]
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute("""INSERT INTO payments (username, user_name, user_role, phone, item_type, item_id, amount, upi_ref, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending Verification')""",
                        (st.session_state.username, st.session_state.full_name, st.session_state.role,
                         st.session_state.phone, m_type, str(m_id), m_price, upi_ref_in.strip()))
                    conn.commit()
                    conn.close()
                    st.success("🎉 Payment record submitted! Admin যাচাই করে approve করবেন।")
        
        st.markdown("---")
        st.markdown("### 📜 আপনার Payment History")
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""SELECT id, item_type, item_id, amount, upi_ref, status, timestamp, admin_note
            FROM payments WHERE username = ? ORDER BY id DESC""", (st.session_state.username,))
        my_pays = cursor.fetchall()
        conn.close()
        
        if not my_pays:
            st.info("এখনো কোনো payment record নেই।")
        else:
            for p_id, itype, iid, amt, uref, stat, ts, note in my_pays:
                color = {"Approved": "🟢", "Pending Verification": "🟡", "Rejected": "🔴"}.get(stat, "⚪")
                with st.expander(f"{color} Payment #{p_id} — {itype} — ₹{amt} [{stat}]"):
                    st.markdown(f"**Item ID:** `{iid}`")
                    st.markdown(f"**UPI Ref:** `{uref}`")
                    st.markdown(f"**Date:** {ts}")
                    if note:
                        st.info(f"Admin Note: {note}")
    
    # ========================================================================
    # STUDENT PORTAL
    # ========================================================================
    elif active_view_role == "student":
        if st_nav == "📖 Practice Center":
            st.subheader("📖 WBBSE Class 10 Geography Practice Center")
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, name FROM topics ORDER BY id ASC")
            topic_dict = {t[1]: t[0] for t in cursor.fetchall()}
            if not topic_dict:
                conn.close()
                st.error("⚠️ কোনো Chapter নেই। Admin কে জানান।")
                st.stop()
            selected_topic_name = st.selectbox("Select Chapter:", list(topic_dict.keys()))
            target_t_id = topic_dict[selected_topic_name]
            cursor.execute("""SELECT id, question_text, question_text_en, option_a, option_a_en, option_b, option_b_en,
                option_c, option_c_en, option_d, option_d_en, correct_option, explanation, explanation_en,
                difficulty, is_descriptive, marks, model_answer, model_answer_en, marking_scheme, marking_scheme_en
                FROM questions WHERE topic_id = ?""", (target_t_id,))
            all_questions = cursor.fetchall()
            conn.close()
            
            if not all_questions:
                st.info("এই chapter এ এখনো কোনো প্রশ্ন যোগ করা হয়নি।")
            else:
                q1_list = [q for q in all_questions if q[16] == 1]
                q2_list = [q for q in all_questions if q[16] == 2]
                q3_list = [q for q in all_questions if q[16] == 3]
                q5_list = [q for q in all_questions if q[16] == 5 or q[16] > 3]
                t1, t2, t3, t5 = st.tabs([
                    f"📁 1 Mark ({len(q1_list)})",
                    f"📁 2 Marks ({len(q2_list)})",
                    f"📁 3 Marks ({len(q3_list)})",
                    f"📁 5 Marks ({len(q5_list)})"
                ])
                
                def render_broad(q_list, mark_label):
                    if not q_list:
                        st.info(f"No {mark_label} questions.")
                        return
                    for idx, q in enumerate(q_list, 1):
                        (q_id, q_bn, q_en, oa_bn, oa_en, ob_bn, ob_en, oc_bn, oc_en, od_bn, od_en,
                         corr_opt, expl_bn, expl_en, diff, is_desc, m_val, m_ans_bn, m_ans_en, ms_bn, ms_en) = q
                        q_label = (q_bn if lang == "Bengali" else q_en) or translate_geo_term(q_bn, lang)
                        st.markdown(f"""<div class="card-broad">
                            <span style="background-color: #7c3aed; color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; float: right;">{m_val} Marks</span>
                            <h4>Q{idx}. {q_label}</h4></div>""", unsafe_allow_html=True)
                        conn = get_connection()
                        cursor = conn.cursor()
                        cursor.execute("SELECT status, teacher_answer FROM student_doubts WHERE student_username = ? AND question_id = ?",
                                       (st.session_state.username, q_id))
                        d_row = cursor.fetchone()
                        conn.close()
                        if d_row and d_row[0] == "Approved" and d_row[1] and d_row[1].strip():
                            st.success("✅ Solution Unlocked!")
                            st.markdown(f"**Model Answer:**\n{d_row[1]}")
                            st.download_button("📥 Download", data=d_row[1], file_name=f"Solution_Q{q_id}.txt", key=f"dl_{q_id}")
                        else:
                            st.caption("🔒 Model Answer hidden.")
                            if st.button(f"🙋 Request Solution for Q{idx}", key=f"req_{q_id}"):
                                conn = get_connection()
                                cursor = conn.cursor()
                                cursor.execute("""INSERT INTO student_doubts (student_username, student_name, question_id, status)
                                    VALUES (?, ?, ?, 'Pending Admin Assignment')""",
                                    (st.session_state.username, st.session_state.full_name, q_id))
                                conn.commit()
                                conn.close()
                                st.success("🎉 Request sent!")
                                st.rerun()
                        st.markdown("<hr/>", unsafe_allow_html=True)
                
                with t1:
                    if not q1_list:
                        st.info("No 1-mark questions.")
                    else:
                        for idx, q in enumerate(q1_list, 1):
                            (q_id, q_bn, q_en, oa_bn, oa_en, ob_bn, ob_en, oc_bn, oc_en, od_bn, od_en,
                             corr_opt, expl_bn, expl_en, diff, is_desc, m_val, m_ans_bn, m_ans_en, ms_bn, ms_en) = q
                            q_label = (q_bn if lang == "Bengali" else q_en) or translate_geo_term(q_bn, lang)
                            st.markdown(f"""<div class="card-short">
                                <span style="background-color: #2563eb; color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; float: right;">1 Mark</span>
                                <h4>Q{idx}. {q_label}</h4></div>""", unsafe_allow_html=True)
                            if oa_bn or oa_en:
                                opts = [
                                    f"A) {(oa_bn if lang == 'Bengali' else oa_en) or translate_geo_term(oa_bn, lang)}",
                                    f"B) {(ob_bn if lang == 'Bengali' else ob_en) or translate_geo_term(ob_bn, lang)}",
                                    f"C) {(oc_bn if lang == 'Bengali' else oc_en) or translate_geo_term(oc_bn, lang)}",
                                    f"D) {(od_bn if lang == 'Bengali' else od_en) or translate_geo_term(od_bn, lang)}"
                                ]
                                user_ans = st.radio(f"Select Q{idx}:", opts, index=None, key=f"std_mcq_{q_id}")
                                if user_ans:
                                    if user_ans[0] == corr_opt:
                                        st.success(f"✅ Correct!")
                                    else:
                                        st.error(f"❌ Correct Answer: {corr_opt}")
                                    st.info(f"💡 {(expl_bn if lang == 'Bengali' else expl_en) or translate_geo_term(expl_bn, lang)}")
                            st.markdown("<hr/>", unsafe_allow_html=True)
                
                with t2: render_broad(q2_list, "2 Marks")
                with t3: render_broad(q3_list, "3 Marks")
                with t5: render_broad(q5_list, "5 Marks")
        
        elif st_nav == "❓ My Help / Doubt Requests":
            st.subheader("❓ My Doubt Requests")
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""SELECT d.id, q.question_text, q.marks, d.status, d.teacher_answer, d.timestamp
                FROM student_doubts d JOIN questions q ON d.question_id = q.id
                WHERE d.student_username = ? ORDER BY d.id DESC""", (st.session_state.username,))
            my_doubts = cursor.fetchall()
            conn.close()
            if not my_doubts:
                st.info("এখনো কোনো doubt request নেই।")
            else:
                for d_id, q_txt, q_m, status, t_ans, t_stamp in my_doubts:
                    with st.expander(f"📌 Doubt #{d_id} [{q_m}M] — {status} ({t_stamp})"):
                        st.markdown(f"**Question:** {q_txt}")
                        if t_ans and t_ans.strip():
                            st.success(f"✅ Solution:\n\n{t_ans}")
                            st.download_button("📥 Download", data=t_ans, file_name=f"Doubt_{d_id}.txt", key=f"d_{d_id}")
                        else:
                            st.info("⏳ Pending resolution.")
        
        elif st_nav == "📄 Mock Tests & Suggestions":
            st.subheader("📄 Mock Tests & Suggestions Portal")
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, test_type, code_num, file_name, file_data, uploader, price, timestamp FROM mock_tests ORDER BY id DESC")
            mocks = cursor.fetchall()
            conn.close()
            if not mocks:
                st.info("এখনো কোনো mock test upload করা হয়নি।")
            else:
                for m_id, t_type, c_num, f_name, f_data, uploader, price, t_stamp in mocks:
                    has_paid = user_has_purchase(st.session_state.username, t_type, m_id)
                    st.markdown(f"### 📄 `{c_num}` — {t_type}")
                    st.caption(f"Uploaded by: {uploader} | Date: {t_stamp} | Price: ₹{price or 0}")
                    if has_paid:
                        st.success("✅ Unlocked!")
                        if f_data:
                            st.download_button(f"📥 Download {c_num}", data=f_data, file_name=f_name, key=f"dl_{m_id}")
                    else:
                        st.markdown(f"""<div class="lock-box">
                            🔒 <strong>Locked!</strong> এই paper দেখতে ₹{price or 0} payment করতে হবে।<br/>
                            <em>Pricing & Payment</em> page থেকে payment করুন।
                        </div>""", unsafe_allow_html=True)
                    st.markdown("---")
        
        elif st_nav == "📝 My Exam Submissions":
            st.subheader("📝 My Exam Submissions")
            st.info("💡 প্রথমে Mock Test unlock করুন, তারপর handwritten answer sheet এর photo/PDF upload করুন।")
            
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, test_type, code_num FROM mock_tests ORDER BY id DESC")
            my_tests = cursor.fetchall()
            conn.close()
            
            unlocked = [(m[0], m[1], m[2]) for m in my_tests if user_has_purchase(st.session_state.username, m[1], m[0])]
            
            if not unlocked:
                st.warning("⚠️ এখনো কোনো Mock Test unlock করেননি।")
            else:
                test_opts = {f"[{t[1]}] {t[2]}": t[0] for t in unlocked}
                sel_test = st.selectbox("কোন Exam এর Answer Sheet submit করবেন?", list(test_opts.keys()), key="sub_exam_sel")
                
                sub_file = st.file_uploader("Answer Sheet Upload (.pdf / .jpg / .png)", type=["pdf", "jpg", "jpeg", "png"], key="sub_answer_file")
                
                if st.button("📤 Submit Answer Sheet to Admin", use_container_width=True, key="sub_ans_btn"):
                    if sub_file is not None:
                        selected_id = test_opts[sel_test]
                        selected_type = sel_test.split("]")[0].strip("[")
                        f_bytes = sub_file.getvalue()
                        conn = get_connection()
                        cursor = conn.cursor()
                        cursor.execute("""INSERT INTO exam_submissions (student_username, student_name, exam_type, exam_code, answer_file_name, answer_file_data, status)
                            VALUES (?, ?, ?, ?, ?, ?, 'Submitted')""",
                            (st.session_state.username, st.session_state.full_name, selected_type,
                             sel_test, sub_file.name, f_bytes))
                        conn.commit()
                        conn.close()
                        st.success("🎉 Answer Sheet submitted! Admin/Teacher check করে ৫ দিনের মধ্যে corrected copy upload করবেন।")
                        st.balloons()
                    else:
                        st.warning("⚠️ File upload করুন।")
            
            st.markdown("---")
            st.markdown("### 📬 আপনার Submitted Answer Sheets")
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""SELECT id, exam_code, answer_file_name, submitted_at, status, corrected_file_name, corrected_file_data, corrected_at, admin_note
                FROM exam_submissions WHERE student_username = ? ORDER BY id DESC""", (st.session_state.username,))
            my_submissions = cursor.fetchall()
            conn.close()
            
            if not my_submissions:
                st.info("এখনো কোনো submission নেই।")
            else:
                for s_id, ecode, afname, sub_at, stat, cfname, cfdata, cat, note in my_submissions:
                    color = "🟢" if stat == "Checked & Returned" else "🟡"
                    with st.expander(f"{color} Submission #{s_id} — {ecode} — {stat}"):
                        st.markdown(f"**Submitted:** {sub_at}")
                        st.markdown(f"**Answer File:** `{afname}`")
                        if note:
                            st.info(f"Admin Note: {note}")
                        if stat == "Checked & Returned" and cfdata:
                            st.success(f"✅ Corrected Copy Available! ({cat})")
                            st.download_button(f"📥 Download Corrected Copy", data=cfdata, file_name=cfname, key=f"dl_corr_{s_id}")
                        else:
                            st.info("⏳ Correction এর অপেক্ষায় (within 5 days)।")
        
        # ---- (remaining student nav items handled by shared blocks above) ----
    
    # ========================================================================
    # TEACHER PORTAL
    # ========================================================================
    elif active_view_role == "teacher":
        if st_nav == "📥 Assigned Student Doubts":
            st.subheader("📥 Doubts Assigned to You")
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""SELECT d.id, d.student_name, q.question_text, q.marks, d.status, d.teacher_answer
                FROM student_doubts d JOIN questions q ON d.question_id = q.id
                WHERE d.assigned_teacher_username = ? ORDER BY d.id DESC""", (st.session_state.username,))
            my_doubts = cursor.fetchall()
            conn.close()
            if not my_doubts:
                st.info("এখনো কোনো doubt assign হয়নি।")
            else:
                for d_id, s_name, q_txt, q_m, status, t_ans in my_doubts:
                    with st.expander(f"📌 Doubt #{d_id} [{q_m}M] — {s_name} — {status}"):
                        st.markdown(f"**Question:** {q_txt}")
                        sol_in = st.text_area(f"Solution for #{d_id}:", value=t_ans, key=f"t_sol_{d_id}")
                        if st.button(f"Submit to Admin", key=f"t_btn_{d_id}"):
                            conn = get_connection()
                            cursor = conn.cursor()
                            cursor.execute("UPDATE student_doubts SET teacher_answer = ?, status = 'Resolved by Teacher (Pending Approval)' WHERE id = ?",
                                           (sol_in.strip(), d_id))
                            conn.commit()
                            conn.close()
                            st.success("🎉 Submitted to Admin!")
                            st.rerun()
        
        elif st_nav == "📖 Question Bank Manager":
            st.subheader("📖 Question Bank Manager")
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, name FROM topics ORDER BY id ASC")
            topic_dict = {t[1]: t[0] for t in cursor.fetchall()}
            conn.close()
            
            if not topic_dict:
                st.error("⚠️ কোনো Chapter নেই।")
                st.stop()
            
            sel_topic_name = st.selectbox("Chapter:", list(topic_dict.keys()), key="tch_top")
            target_t_id = topic_dict[sel_topic_name]
            
            tab_man, tab_dups, tab_del = st.tabs([
                "➕ Manual Question Upload",
                "🔍 Duplicate Remover",
                "📖 Browse & Delete"
            ])
            
            with tab_man:
                st.markdown("### ➕ Manual Question Upload")
                q_text_bn = st.text_area("Question (Bengali):", key="tch_q_bn")
                q_marks = st.selectbox("Marks:", [1, 2, 3, 5], key="tch_q_marks")
                if q_text_bn.strip():
                    match, ratio = check_duplicate_question(q_text_bn, target_t_id)
                    if match:
                        st.warning(f"⚠️ Similar Question Found ({ratio*100:.1f}%): Q_ID #{match[0]}")
                if q_marks == 1:
                    col1, col2 = st.columns(2)
                    oa = col1.text_input("Option A:", key="tch_oa")
                    ob = col2.text_input("Option B:", key="tch_ob")
                    oc = col1.text_input("Option C:", key="tch_oc")
                    od = col2.text_input("Option D:", key="tch_od")
                    corr_opt = st.selectbox("Correct:", ["A", "B", "C", "D"], key="tch_co")
                    expl = st.text_area("Explanation:", key="tch_ex")
                    if st.button("Save MCQ", key="tch_save_mcq"):
                        if q_text_bn and oa:
                            conn = get_connection()
                            cursor = conn.cursor()
                            cursor.execute("""INSERT INTO questions (topic_id, question_text, question_text_en, option_a, option_b, option_c, option_d, correct_option, explanation, difficulty, is_descriptive, marks)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Medium', 0, 1)""",
                                (target_t_id, q_text_bn, translate_geo_term(q_text_bn, "English"), oa, ob, oc, od, corr_opt, expl))
                            conn.commit()
                            conn.close()
                            st.success("✅ Added!")
                            st.rerun()
                else:
                    m_ans = st.text_area(f"Model Answer ({q_marks}M):", key="tch_ma")
                    m_sch = st.text_area("Marking Scheme:", key="tch_ms")
                    if st.button("Save Broad Question", key="tch_save_broad"):
                        if q_text_bn:
                            conn = get_connection()
                            cursor = conn.cursor()
                            cursor.execute("""INSERT INTO questions (topic_id, question_text, question_text_en, difficulty, is_descriptive, marks, model_answer, marking_scheme)
                                VALUES (?, ?, ?, 'Hard', 1, ?, ?, ?)""",
                                (target_t_id, q_text_bn, translate_geo_term(q_text_bn, "English"), q_marks, m_ans, m_sch))
                            conn.commit()
                            conn.close()
                            st.success("✅ Added!")
                            st.rerun()
            
            with tab_dups:
                st.markdown("### 🔍 Auto Duplicate Scanner (75%+ similarity)")
                if st.button("🔍 Scan Chapter", key="tch_scan"):
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT id, question_text, marks FROM questions WHERE topic_id = ? ORDER BY id ASC", (target_t_id,))
                    all_q = cursor.fetchall()
                    conn.close()
                    if len(all_q) < 2:
                        st.warning("কমপক্ষে ২টি প্রশ্ন লাগবে।")
                    else:
                        import difflib
                        groups = []
                        processed = set()
                        for i in range(len(all_q)):
                            if all_q[i][0] in processed: continue
                            grp = [all_q[i]]
                            for j in range(i + 1, len(all_q)):
                                if all_q[j][0] in processed: continue
                                t1 = re.sub(r'[^\w\s]', '', normalize_bengali_text(all_q[i][1])).lower()
                                t2 = re.sub(r'[^\w\s]', '', normalize_bengali_text(all_q[j][1])).lower()
                                if difflib.SequenceMatcher(None, t1, t2).ratio() >= 0.75:
                                    grp.append(all_q[j]); processed.add(all_q[j][0])
                            if len(grp) > 1:
                                processed.add(all_q[i][0]); groups.append(grp)
                        if not groups:
                            st.success("🎉 কোনো duplicate নেই!")
                        else:
                            st.warning(f"⚠️ {len(groups)} Duplicate Group!")
                            for gi, grp in enumerate(groups, 1):
                                st.markdown(f"#### Group #{gi}")
                                keep_id = st.radio(f"Keep which in G#{gi}?", [q[0] for q in grp],
                                    format_func=lambda x: next(f"#{q[0]} [{q[2]}M]: {q[1][:80]}" for q in grp if q[0] == x),
                                    key=f"keep_{gi}_tch")
                                for q in grp:
                                    colA, colB = st.columns([5, 1])
                                    color = "#16a34a" if q[0] == keep_id else "#dc2626"
                                    prefix = "✅ KEEP" if q[0] == keep_id else "❌ DUP"
                                    colA.markdown(f"<span style='color:{color};font-weight:bold;'>{prefix}</span> #{q[0]}: {q[1]}")
                                    if q[0] != keep_id and colB.button(f"🗑️ Del #{q[0]}", key=f"d_{q[0]}_tch"):
                                        conn = get_connection()
                                        cursor = conn.cursor()
                                        cursor.execute("INSERT INTO duplicate_log (original_q_id, duplicate_q_id, similarity, removed_by) VALUES (?, ?, ?, ?)",
                                                       (keep_id, q[0], 100.0, st.session_state.full_name))
                                        cursor.execute("DELETE FROM questions WHERE id = ?", (q[0],))
                                        conn.commit()
                                        conn.close()
                                        st.success(f"Deleted #{q[0]}")
                                        st.rerun()
                                st.markdown("---")
            
            with tab_del:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id, question_text, marks FROM questions WHERE topic_id = ? ORDER BY id DESC", (target_t_id,))
                q_rows = cursor.fetchall()
                conn.close()
                if not q_rows:
                    st.info("No questions.")
                else:
                    for q_id, q_txt, q_m in q_rows:
                        c1, c2 = st.columns([5, 1])
                        c1.markdown(f"**#{q_id} [{q_m}M]:** {q_txt}")
                        if c2.button(f"🗑️ #{q_id}", key=f"td_{q_id}"):
                            conn = get_connection()
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM questions WHERE id = ?", (q_id,))
                            conn.commit()
                            conn.close()
                            st.rerun()
        
        elif st_nav == "📄 Upload Mock Tests & Suggestions":
            st.subheader("📄 Upload Mock Tests & Suggestions")
            t_type = st.radio("Type:", ["Chapter Wise Mock Test", "Final Mock Test", "Board Suggestions"], horizontal=True, key="tch_mock_type")
            
            default_price = {"Chapter Wise Mock Test": 19, "Final Mock Test": 49, "Board Suggestions": 69}[t_type]
            price = st.number_input(f"Price (₹) — Default ₹{default_price}", min_value=0, value=default_price, step=1, key="tch_mock_price")
            
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM mock_tests WHERE test_type = ?", (t_type,))
            cnt = cursor.fetchone()[0]
            conn.close()
            prefix = "chapter mock" if t_type == "Chapter Wise Mock Test" else ("final mock" if t_type == "Final Mock Test" else "suggestion")
            auto_code = f"{prefix} - {cnt + 1:03d}"
            st.info(f"Generated Code: `{auto_code}`")
            up_file = st.file_uploader("Upload (.pdf / .docx)", type=["pdf", "docx"], key="tch_mock_up")
            if st.button("🚀 Publish", key="tch_mock_pub"):
                if up_file:
                    f_bytes = up_file.getvalue()
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute("""INSERT INTO mock_tests (test_type, code_num, file_name, file_data, uploader, price)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                        (t_type, auto_code, up_file.name, f_bytes, st.session_state.full_name, price))
                    conn.commit()
                    conn.close()
                    st.success(f"🎉 Published `{auto_code}`!")
                    st.rerun()
        
        elif st_nav == "📝 Check Student Answer Sheets":
            st.subheader("📝 Check Student Answer Sheets")
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""SELECT id, student_name, exam_code, answer_file_name, answer_file_data, submitted_at, status, admin_note
                FROM exam_submissions WHERE status IN ('Submitted', 'Under Check') ORDER BY id ASC""")
            subs = cursor.fetchall()
            conn.close()
            
            if not subs:
                st.info("📭 কোনো pending submission নেই।")
            else:
                st.warning(f"⚠️ {len(subs)}টি submission check এর জন্য অপেক্ষা করছে। Admin assigned করলে আপনি correction upload করতে পারবেন।")
                for s_id, s_name, ecode, afname, afdata, sub_at, stat, note in subs:
                    with st.expander(f"📄 Submission #{s_id} — {s_name} — {ecode} — {stat}"):
                        st.markdown(f"**Submitted:** {sub_at}")
                        if afdata:
                            st.download_button("📥 Download Answer Sheet", data=afdata, file_name=afname, key=f"tch_dl_ans_{s_id}")
                        st.info("🔒 Correction upload করতে Admin approval লাগবে। Admin এর 'Exam Answer Sheet Checking' section থেকে authorize করলে এখানে upload option আসবে।")
        
        elif st_nav == "👨‍🏫 Student Track Records":
            st.subheader("👨‍🏫 Student Track Records")
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""SELECT student_name, student_phone, school_name, district, exam_name, topic_name, score, total_questions, percentage, timestamp
                FROM student_scores ORDER BY timestamp DESC""")
            scores = cursor.fetchall()
            conn.close()
            if not scores:
                st.info("No records.")
            else:
                df = pd.DataFrame(scores, columns=["Name", "Phone", "School", "District", "Exam", "Topic", "Score", "Total", "Pct", "Timestamp"])
                st.dataframe(df, use_container_width=True)
    
    # ========================================================================
    # ADMIN PORTAL
    # ========================================================================
    elif active_view_role == "admin":
        if st_nav == "🛡️ User Approvals":
            st.subheader("🛡️ User Approvals")
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""SELECT id, role, full_name, school_name, class_grade, phone, district, approved
                FROM users WHERE is_admin = 0 ORDER BY approved ASC, id DESC""")
            all_u = cursor.fetchall()
            conn.close()
            if not all_u:
                st.info("No users.")
            else:
                df_u = pd.DataFrame(all_u, columns=["ID", "Role", "Name", "School", "Class", "Phone", "District", "Approved"])
                st.dataframe(df_u, use_container_width=True)
                sel_uid = st.number_input("User ID:", min_value=1, step=1, key="adm_uid")
                c1, c2 = st.columns(2)
                if c1.button("✅ Approve", use_container_width=True):
                    conn = get_connection(); cursor = conn.cursor()
                    cursor.execute("UPDATE users SET approved = 1 WHERE id = ?", (sel_uid,))
                    conn.commit(); conn.close()
                    st.success(f"Approved #{sel_uid}"); st.rerun()
                if c2.button("🚫 Revoke", use_container_width=True):
                    conn = get_connection(); cursor = conn.cursor()
                    cursor.execute("UPDATE users SET approved = 0 WHERE id = ?", (sel_uid,))
                    conn.commit(); conn.close()
                    st.warning(f"Revoked #{sel_uid}"); st.rerun()
        
        elif st_nav == "❓ Student Doubt Assignment Hub":
            st.subheader("❓ Doubt Assignment Hub")
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""SELECT d.id, d.student_name, q.question_text, q.marks, d.assigned_teacher_username, d.teacher_answer, d.status
                FROM student_doubts d JOIN questions q ON d.question_id = q.id ORDER BY d.id DESC""")
            doubts = cursor.fetchall()
            cursor.execute("SELECT username, full_name FROM users WHERE role = 'teacher' AND approved = 1")
            teachers = cursor.fetchall()
            teacher_map = {f"{t[1]} ({t[0]})": t[0] for t in teachers}
            conn.close()
            
            if not doubts:
                st.info("No doubts.")
            else:
                df_d = pd.DataFrame(doubts, columns=["ID", "Student", "Question", "Marks", "Assigned", "Answer", "Status"])
                st.dataframe(df_d, use_container_width=True)
                sel_d_id = st.number_input("Doubt ID:", min_value=1, step=1, key="adm_did")
                conn = get_connection(); cursor = conn.cursor()
                cursor.execute("""SELECT d.id, d.student_name, q.question_text, q.marks, d.assigned_teacher_username, d.teacher_answer, d.status
                    FROM student_doubts d JOIN questions q ON d.question_id = q.id WHERE d.id = ?""", (sel_d_id,))
                row = cursor.fetchone()
                conn.close()
                if row:
                    d_id, s_name, q_txt, q_m, t_user, t_ans, d_stat = row
                    st.markdown(f"### Doubt #{d_id} [{q_m}M]")
                    st.markdown(f"**Student:** {s_name} | **Status:** `{d_stat}`")
                    st.markdown(f"**Question:** {q_txt}")
                    if t_ans and t_ans.strip():
                        st.markdown("#### Teacher Submitted Solution:")
                        rev_ans = st.text_area("Review:", value=t_ans, height=150, key=f"rev_{d_id}")
                        if st.button("✅ Approve & Unlock", key=f"appr_{d_id}", use_container_width=True):
                            conn = get_connection(); cursor = conn.cursor()
                            cursor.execute("UPDATE student_doubts SET teacher_answer = ?, status = 'Approved' WHERE id = ?", (rev_ans.strip(), d_id))
                            conn.commit(); conn.close()
                            st.success("Approved!"); st.rerun()
                    else:
                        st.caption("No teacher answer yet.")
                    st.markdown("---")
                    ca, cb = st.columns(2)
                    with ca:
                        st.markdown("#### Assign to Teacher")
                        if teacher_map:
                            sel_t = st.selectbox("Teacher:", list(teacher_map.keys()), key=f"t_{d_id}")
                            if st.button("Assign", key=f"as_{d_id}"):
                                conn = get_connection(); cursor = conn.cursor()
                                cursor.execute("UPDATE student_doubts SET assigned_teacher_username = ?, status = 'Assigned to Teacher' WHERE id = ?",
                                               (teacher_map[sel_t], d_id))
                                conn.commit(); conn.close()
                                st.success("Assigned!"); st.rerun()
                    with cb:
                        st.markdown("#### Solve Directly")
                        direct_ans = st.text_area("Solution:", key=f"dir_{d_id}")
                        if st.button("Approve Admin Solution", key=f"adap_{d_id}"):
                            if direct_ans.strip():
                                conn = get_connection(); cursor = conn.cursor()
                                cursor.execute("UPDATE student_doubts SET teacher_answer = ?, status = 'Approved' WHERE id = ?",
                                               (direct_ans.strip(), d_id))
                                conn.commit(); conn.close()
                                st.success("Approved!"); st.rerun()
        
        elif st_nav == "📖 Question Bank Manager":
            st.subheader("📖 Question Bank Manager")
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, name FROM topics ORDER BY id ASC")
            topic_dict = {t[1]: t[0] for t in cursor.fetchall()}
            conn.close()
            if not topic_dict:
                st.error("No chapters."); st.stop()
            
            sel_topic_name = st.selectbox("Chapter:", list(topic_dict.keys()), key="adm_top")
            target_t_id = topic_dict[sel_topic_name]
            
            tab_ext, tab_man, tab_dups, tab_del = st.tabs([
                "⚡ PDF/URL Extractor",
                "➕ Manual Upload",
                "🔍 Duplicate Remover",
                "📖 Browse & Delete"
            ])
            
            with tab_ext:
                st.markdown("### 📤 Auto-Extract Engine")
                st.markdown("""
                **⚠️ Bengali Font Warning:** PDF-এ SutonnyMJ/Nikosh font থাকলে extracted text ভাঙা আসবে। 
                **Best Practice:** DOCX upload করুন, অথবা Manual Text Paste ব্যবহার করুন।
                """)
                source_type = st.radio("Source:", ["📄 Manual Text Paste (Best for Bengali)", "📁 PDF / DOCX File", "🌐 Website URL"], horizontal=False, key="adm_src")
                extracted_text = ""
                
                if source_type == "📄 Manual Text Paste (Best for Bengali)":
                    st.info("PDF থেকে text select → Ctrl+C → এখানে Ctrl+V করুন। Bengali perfect আসবে!")
                    manual_txt = st.text_area("Paste Here:", height=250, key="adm_manual_paste",
                        placeholder="Q1. সর্বপ্রথম ভূবিজ্ঞান কে প্রতিষ্ঠা করেন?\n(ক) ...\n(খ) ...")
                    if manual_txt.strip():
                        extracted_text = normalize_bengali_text(manual_txt)
                elif source_type == "📁 PDF / DOCX File":
                    file_obj = st.file_uploader("Upload", type=["pdf", "docx"], key="adm_upl")
                    if file_obj is not None:
                        ext = file_obj.name.split('.')[-1].lower()
                        if ext == "pdf":
                            extracted_text = extract_text_from_pdf_file(file_obj)
                        elif ext == "docx" and HAS_DOCX:
                            doc_file = docx.Document(file_obj)
                            raw = "\n".join([p.text for p in doc_file.paragraphs if p.text.strip()])
                            extracted_text = normalize_bengali_text(raw)
                else:
                    web_url = st.text_input("URL:", key="adm_url")
                    if st.button("🌐 Fetch"):
                        if web_url.strip():
                            try:
                                req = urllib.request.Request(web_url.strip(), headers={'User-Agent': 'Mozilla/5.0'})
                                with urllib.request.urlopen(req, timeout=10) as resp:
                                    html = resp.read().decode('utf-8', errors='ignore')
                                    raw = re.sub(r'<[^>]+>', ' ', html)
                                    extracted_text = normalize_bengali_text(raw)
                                    st.success("Fetched!")
                            except Exception as e:
                                st.error(f"Error: {e}")
                
                if extracted_text:
                    st.markdown("#### 📝 Preview (Editable):")
                    edited = st.text_area("Review:", value=extracted_text, height=200, key="adm_edit")
                    parsed = parse_and_categorize_questions(edited)
                    st.success(f"Extracted {len(parsed)} questions!")
                    m1 = [q for q in parsed if q["marks"] == 1]
                    m2 = [q for q in parsed if q["marks"] == 2]
                    m3 = [q for q in parsed if q["marks"] == 3]
                    m5 = [q for q in parsed if q["marks"] == 5]
                    f1, f2, f3, f5 = st.tabs([f"1M ({len(m1)})", f"2M ({len(m2)})", f"3M ({len(m3)})", f"5M ({len(m5)})"])
                    with f1: 
                        if m1: st.dataframe(pd.DataFrame(m1), use_container_width=True)
                    with f2: 
                        if m2: st.dataframe(pd.DataFrame(m2), use_container_width=True)
                    with f3: 
                        if m3: st.dataframe(pd.DataFrame(m3), use_container_width=True)
                    with f5: 
                        if m5: st.dataframe(pd.DataFrame(m5), use_container_width=True)
                    if st.button("🚀 Save All", key="adm_save_all"):
                        conn = get_connection(); cursor = conn.cursor()
                        saved = 0
                        for q in parsed:
                            q_bn = q["question"]
                            q_en = translate_geo_term(q_bn, "English")
                            cursor.execute("""INSERT INTO questions (topic_id, question_text, question_text_en, option_a, option_b, option_c, option_d, correct_option, explanation, difficulty, is_descriptive, marks, model_answer, marking_scheme)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Medium', ?, ?, ?, ?)""",
                                (target_t_id, q_bn, q_en, q["opt_a"], q["opt_b"], q["opt_c"], q["opt_d"],
                                 q["correct"], q["explanation"], q["is_descriptive"], q["marks"],
                                 q_bn if q["is_descriptive"] else "", f"{q['marks']}M Scheme"))
                            saved += 1
                        conn.commit(); conn.close()
                        st.success(f"Saved {saved} questions!")
                        st.rerun()
            
            with tab_man:
                st.markdown("### ➕ Manual Upload")
                q_text_bn = st.text_area("Question:", key="adm_q_bn")
                q_marks = st.selectbox("Marks:", [1, 2, 3, 5], key="adm_q_m")
                if q_text_bn.strip():
                    match, ratio = check_duplicate_question(q_text_bn, target_t_id)
                    if match:
                        st.warning(f"⚠️ Duplicate ({ratio*100:.1f}%): Q_ID #{match[0]}")
                if q_marks == 1:
                    c1, c2 = st.columns(2)
                    oa = c1.text_input("A:", key="adm_oa")
                    ob = c2.text_input("B:", key="adm_ob")
                    oc = c1.text_input("C:", key="adm_oc")
                    od = c2.text_input("D:", key="adm_od")
                    co = st.selectbox("Correct:", ["A", "B", "C", "D"], key="adm_co2")
                    ex = st.text_area("Explanation:", key="adm_ex2")
                    if st.button("Save MCQ", key="adm_save_mcq2"):
                        if q_text_bn and oa:
                            conn = get_connection(); cursor = conn.cursor()
                            cursor.execute("""INSERT INTO questions (topic_id, question_text, question_text_en, option_a, option_b, option_c, option_d, correct_option, explanation, difficulty, is_descriptive, marks)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Medium', 0, 1)""",
                                (target_t_id, q_text_bn, translate_geo_term(q_text_bn, "English"), oa, ob, oc, od, co, ex))
                            conn.commit(); conn.close()
                            st.success("Added!"); st.rerun()
                else:
                    ma = st.text_area(f"Model Answer ({q_marks}M):", key="adm_ma2")
                    ms = st.text_area("Marking Scheme:", key="adm_ms2")
                    if st.button(f"Save {q_marks}M Question", key="adm_save_b"):
                        if q_text_bn:
                            conn = get_connection(); cursor = conn.cursor()
                            cursor.execute("""INSERT INTO questions (topic_id, question_text, question_text_en, difficulty, is_descriptive, marks, model_answer, marking_scheme)
                                VALUES (?, ?, ?, 'Hard', 1, ?, ?, ?)""",
                                (target_t_id, q_text_bn, translate_geo_term(q_text_bn, "English"), q_marks, ma, ms))
                            conn.commit(); conn.close()
                            st.success("Added!"); st.rerun()
            
            with tab_dups:
                st.markdown("### 🔍 Duplicate Remover (75%+ similarity)")
                if st.button("🔍 Scan Chapter", key="adm_scan"):
                    conn = get_connection(); cursor = conn.cursor()
                    cursor.execute("SELECT id, question_text, marks FROM questions WHERE topic_id = ? ORDER BY id ASC", (target_t_id,))
                    all_q = cursor.fetchall(); conn.close()
                    if len(all_q) < 2:
                        st.warning("২টি প্রশ্ন লাগবে।")
                    else:
                        import difflib
                        groups = []; processed = set()
                        for i in range(len(all_q)):
                            if all_q[i][0] in processed: continue
                            grp = [all_q[i]]
                            for j in range(i + 1, len(all_q)):
                                if all_q[j][0] in processed: continue
                                t1 = re.sub(r'[^\w\s]', '', normalize_bengali_text(all_q[i][1])).lower()
                                t2 = re.sub(r'[^\w\s]', '', normalize_bengali_text(all_q[j][1])).lower()
                                if difflib.SequenceMatcher(None, t1, t2).ratio() >= 0.75:
                                    grp.append(all_q[j]); processed.add(all_q[j][0])
                            if len(grp) > 1:
                                processed.add(all_q[i][0]); groups.append(grp)
                        if not groups:
                            st.success("🎉 No duplicates!")
                        else:
                            st.warning(f"⚠️ {len(groups)} Duplicate Groups!")
                            for gi, grp in enumerate(groups, 1):
                                st.markdown(f"#### Group #{gi}")
                                keep = st.radio(f"Keep in G#{gi}?", [q[0] for q in grp],
                                    format_func=lambda x: next(f"#{q[0]} [{q[2]}M]: {q[1][:80]}" for q in grp if q[0] == x),
                                    key=f"k_{gi}_adm")
                                for q in grp:
                                    cA, cB = st.columns([5, 1])
                                    color = "#16a34a" if q[0] == keep else "#dc2626"
                                    prefix = "✅ KEEP" if q[0] == keep else "❌ DUP"
                                    cA.markdown(f"<span style='color:{color};font-weight:bold;'>{prefix}</span> #{q[0]}: {q[1]}")
                                    if q[0] != keep and cB.button(f"🗑️ #{q[0]}", key=f"d_{q[0]}_adm"):
                                        conn = get_connection(); cursor = conn.cursor()
                                        cursor.execute("INSERT INTO duplicate_log (original_q_id, duplicate_q_id, similarity, removed_by) VALUES (?, ?, ?, ?)",
                                                       (keep, q[0], 100.0, st.session_state.full_name))
                                        cursor.execute("DELETE FROM questions WHERE id = ?", (q[0],))
                                        conn.commit(); conn.close()
                                        st.success(f"Deleted #{q[0]}"); st.rerun()
                                st.markdown("---")
            
            with tab_del:
                conn = get_connection(); cursor = conn.cursor()
                cursor.execute("SELECT id, question_text, marks FROM questions WHERE topic_id = ? ORDER BY id DESC", (target_t_id,))
                q_rows = cursor.fetchall(); conn.close()
                if not q_rows:
                    st.info("No questions.")
                else:
                    for q_id, q_txt, q_m in q_rows:
                        c1, c2 = st.columns([5, 1])
                        c1.markdown(f"**#{q_id} [{q_m}M]:** {q_txt}")
                        if c2.button(f"🗑️ #{q_id}", key=f"ad_{q_id}"):
                            conn = get_connection(); cursor = conn.cursor()
                            cursor.execute("DELETE FROM questions WHERE id = ?", (q_id,))
                            conn.commit(); conn.close()
                            st.rerun()
        
        elif st_nav == "📄 Upload Mock Tests & Suggestions":
            st.subheader("📄 Upload Mock Tests & Suggestions")
            t_type = st.radio("Type:", ["Chapter Wise Mock Test", "Final Mock Test", "Board Suggestions"], horizontal=True, key="adm_mt")
            default_price = {"Chapter Wise Mock Test": 19, "Final Mock Test": 49, "Board Suggestions": 69}[t_type]
            price = st.number_input(f"Price (₹)", min_value=0, value=default_price, step=1, key="adm_mp")
            conn = get_connection(); cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM mock_tests WHERE test_type = ?", (t_type,))
            cnt = cursor.fetchone()[0]; conn.close()
            prefix = "chapter mock" if t_type == "Chapter Wise Mock Test" else ("final mock" if t_type == "Final Mock Test" else "suggestion")
            auto_code = f"{prefix} - {cnt + 1:03d}"
            st.info(f"Code: `{auto_code}`")
            up_file = st.file_uploader("Upload (.pdf / .docx)", type=["pdf", "docx"], key="adm_mu")
            if st.button("🚀 Publish", key="adm_mpub"):
                if up_file:
                    f_bytes = up_file.getvalue()
                    conn = get_connection(); cursor = conn.cursor()
                    cursor.execute("""INSERT INTO mock_tests (test_type, code_num, file_name, file_data, uploader, price)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                        (t_type, auto_code, up_file.name, f_bytes, st.session_state.full_name, price))
                    conn.commit(); conn.close()
                    st.success(f"Published `{auto_code}`!"); st.rerun()
        
        elif st_nav == "💡 Ask Corner Suggestions":
            st.subheader("💡 Ask Corner — Suggestions Hub")
            conn = get_connection(); cursor = conn.cursor()
            cursor.execute("""SELECT id, submitter_name, submitter_role, category, message, admin_reply, status, timestamp
                FROM ask_corner ORDER BY id DESC""")
            asks = cursor.fetchall(); conn.close()
            if not asks:
                st.info("No suggestions yet.")
            else:
                c1, c2, c3 = st.columns(3)
                c1.metric("📨 Total", len(asks))
                c2.metric("🆕 New", sum(1 for a in asks if a[6] == "New"))
                c3.metric("✅ Replied", sum(1 for a in asks if a[6] == "Replied"))
                st.markdown("---")
                for a_id, name, role_s, cat, msg, rep, stat, ts in asks:
                    color = "#16a34a" if stat == "Replied" else "#dc2626"
                    st.markdown(f"""
                        <div class="ask-corner-card" style="border-left-color:{color};">
                        <span style="background:{color};color:white;padding:3px 8px;border-radius:5px;font-size:12px;font-weight:bold;">{stat}</span>
                        <strong style="margin-left:10px;">#{a_id} — {cat}</strong><br/>
                        <small>👤 {name} ({role_s}) — {ts}</small>
                        </div>""", unsafe_allow_html=True)
                    st.markdown(f"**Message:** {msg}")
                    reply_text = st.text_area(f"Reply #{a_id}:", value=rep, key=f"ar_{a_id}", height=100)
                    cA, cB = st.columns(2)
                    if cA.button(f"📤 Send Reply", key=f"sr_{a_id}"):
                        conn = get_connection(); cursor = conn.cursor()
                        cursor.execute("UPDATE ask_corner SET admin_reply = ?, status = 'Replied' WHERE id = ?",
                                       (reply_text.strip(), a_id))
                        conn.commit(); conn.close()
                        st.success(f"Reply sent #{a_id}"); st.rerun()
                    if cB.button(f"🗑️ Delete #{a_id}", key=f"da_{a_id}"):
                        conn = get_connection(); cursor = conn.cursor()
                        cursor.execute("DELETE FROM ask_corner WHERE id = ?", (a_id,))
                        conn.commit(); conn.close(); st.rerun()
                    st.markdown("---")
        
        elif st_nav == "💳 Payment Verifications":
            st.subheader("💳 Payment Verifications")
            conn = get_connection(); cursor = conn.cursor()
            cursor.execute("""SELECT id, user_name, user_role, phone, item_type, item_id, amount, upi_ref, status, timestamp, admin_note
                FROM payments ORDER BY CASE WHEN status='Pending Verification' THEN 0 ELSE 1 END, id DESC""")
            pays = cursor.fetchall(); conn.close()
            
            if not pays:
                st.info("No payments yet.")
            else:
                pending = [p for p in pays if p[8] == "Pending Verification"]
                if pending:
                    st.warning(f"🔔 {len(pending)}টি payment verification এর অপেক্ষায়!")
                c1, c2, c3 = st.columns(3)
                c1.metric("Total", len(pays))
                c2.metric("Pending", len(pending))
                c3.metric("Approved", sum(1 for p in pays if p[8] == "Approved"))
                st.markdown("---")
                
                for p_id, uname, urole, phone, itype, iid, amt, uref, stat, ts, note in pays:
                    color = {"Approved": "🟢", "Pending Verification": "🟡", "Rejected": "🔴"}.get(stat, "⚪")
                    with st.expander(f"{color} Payment #{p_id} — {uname} ({urole}) — ₹{amt} [{stat}]"):
                        st.markdown(f"**Phone:** {phone}")
                        st.markdown(f"**Item:** {itype} (ID: {iid})")
                        st.markdown(f"**UPI Ref:** `{uref}`")
                        st.markdown(f"**Time:** {ts}")
                        if note:
                            st.info(f"Note: {note}")
                        
                        if stat == "Pending Verification":
                            st.markdown("#### ✅ Verify this payment in your UPI/Bank app before approving!")
                            adm_note = st.text_input(f"Note (optional):", key=f"pn_{p_id}")
                            cb1, cb2 = st.columns(2)
                            if cb1.button(f"✅ Approve & Unlock for {uname}", key=f"pa_{p_id}", use_container_width=True):
                                conn = get_connection(); cursor = conn.cursor()
                                cursor.execute("UPDATE payments SET status = 'Approved', approved_at = CURRENT_TIMESTAMP, admin_note = ? WHERE id = ?",
                                               (adm_note.strip(), p_id))
                                cursor.execute("""INSERT INTO user_purchases (username, item_type, item_id, payment_id, status)
                                    VALUES (?, ?, ?, ?, 'Active')""",
                                    (uname, itype, str(iid), p_id))
                                conn.commit(); conn.close()
                                st.success(f"✅ Approved! Item unlocked for {uname}")
                                st.balloons()
                                st.rerun()
                            if cb2.button(f"❌ Reject", key=f"pr_{p_id}", use_container_width=True):
                                conn = get_connection(); cursor = conn.cursor()
                                cursor.execute("UPDATE payments SET status = 'Rejected', admin_note = ? WHERE id = ?",
                                               (adm_note.strip(), p_id))
                                conn.commit(); conn.close()
                                st.warning(f"Rejected #{p_id}"); st.rerun()
        
        elif st_nav == "📝 Exam Answer Sheet Checking":
            st.subheader("📝 Exam Answer Sheet Checking")
            conn = get_connection(); cursor = conn.cursor()
            cursor.execute("""SELECT id, student_username, student_name, exam_code, answer_file_name, answer_file_data, submitted_at, checker_username, status, admin_note
                FROM exam_submissions ORDER BY id DESC""")
            subs = cursor.fetchall()
            cursor.execute("SELECT username, full_name FROM users WHERE role = 'teacher' AND approved = 1")
            teachers = cursor.fetchall()
            teacher_map = {f"{t[1]} ({t[0]})": t[0] for t in teachers}
            conn.close()
            
            if not subs:
                st.info("No submissions yet.")
            else:
                df = pd.DataFrame([(s[0], s[2], s[3], s[6], s[8]) for s in subs],
                                  columns=["ID", "Student", "Exam Code", "Submitted", "Status"])
                st.dataframe(df, use_container_width=True)
                st.markdown("---")
                
                for s_id, suname, sname, ecode, afname, afdata, sub_at, checker, stat, note in subs:
                    with st.expander(f"📄 #{s_id} — {sname} — {ecode} — [{stat}] — {sub_at}"):
                        if afdata:
                            st.download_button("📥 Download Student Answer Sheet", data=afdata, file_name=afname, key=f"adm_dl_{s_id}")
                        
                        st.markdown("#### Assigned Checker (optional)")
                        if teacher_map:
                            t_options = ["-- None --"] + list(teacher_map.keys())
                            sel_t_idx = 0
                            if checker:
                                for i, k in enumerate(t_options):
                                    if teacher_map.get(k) == checker: sel_t_idx = i; break
                            sel_t = st.selectbox("Checker:", t_options, index=sel_t_idx, key=f"chk_{s_id}")
                            if sel_t != "-- None --":
                                if st.button("Assign Checker", key=f"asg_{s_id}"):
                                    conn = get_connection(); cursor = conn.cursor()
                                    cursor.execute("UPDATE exam_submissions SET checker_username = ?, status = 'Under Check' WHERE id = ?",
                                                   (teacher_map[sel_t], s_id))
                                    conn.commit(); conn.close()
                                    st.success("Assigned!"); st.rerun()
                        
                        st.markdown("#### Upload Corrected Copy")
                        corr_file = st.file_uploader("Corrected Answer Sheet (.pdf / .jpg / .png)", 
                                                     type=["pdf", "jpg", "jpeg", "png"], key=f"cf_{s_id}")
                        adm_note = st.text_input("Note for Student:", key=f"an_{s_id}")
                        
                        cb1, cb2 = st.columns(2)
                        if cb1.button("✅ Upload Corrected & Notify Student", key=f"uc_{s_id}", use_container_width=True):
                            if corr_file is not None:
                                cf_bytes = corr_file.getvalue()
                                conn = get_connection(); cursor = conn.cursor()
                                cursor.execute("""UPDATE exam_submissions 
                                    SET corrected_file_name = ?, corrected_file_data = ?, corrected_at = CURRENT_TIMESTAMP,
                                        status = 'Checked & Returned', admin_note = ?
                                    WHERE id = ?""",
                                    (corr_file.name, cf_bytes, adm_note.strip(), s_id))
                                conn.commit(); conn.close()
                                st.success("🎉 Corrected copy uploaded & student notified!")
                                st.rerun()
                            else:
                                st.warning("⚠️ File upload করুন।")
                        if cb2.button("🗑️ Delete Submission", key=f"ds_{s_id}", use_container_width=True):
                            conn = get_connection(); cursor = conn.cursor()
                            cursor.execute("DELETE FROM exam_submissions WHERE id = ?", (s_id,))
                            conn.commit(); conn.close()
                            st.rerun()
        
        elif st_nav == "📊 Analytics & Track Records":
            st.subheader("📊 Analytics & Track Records")
            conn = get_connection(); cursor = conn.cursor()
            cursor.execute("""SELECT student_name, student_phone, school_name, district, exam_name, topic_name, score, total_questions, percentage, timestamp
                FROM student_scores ORDER BY timestamp DESC""")
            scores = cursor.fetchall(); conn.close()
            if not scores:
                st.info("No records.")
            else:
                df = pd.DataFrame(scores, columns=["Name", "Phone", "School", "District", "Exam", "Topic", "Score", "Total", "Pct", "Timestamp"])
                st.dataframe(df, use_container_width=True)

# ============================================================================
# FOOTER
# ============================================================================
st.markdown("""
    <div class="footer-block">
        <h3 style="margin-bottom: 5px; color: #38bdf8;">Prepared by - Shawon Kar, Sukannya Chakraborty</h3>
        <p style="margin: 3px 0; font-size: 1.1em; font-weight: 500;">M.Sc. in Geography (University Of Calcutta)</p>
        <p style="margin: 3px 0; font-size: 1.0em; color: #94a3b8;">B.Ed. (Baba Saheb Ambedkar Education University)</p>
        <p style="margin: 10px 0 0 0; font-weight: bold; color: #38bdf8; font-size: 1.2em;">📞 Ph No - 7001257277</p>
    </div>
""", unsafe_allow_html=True)
