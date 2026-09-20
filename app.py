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

# Safe imports for optional third-party packages to prevent startup crashes
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

# Set Streamlit Page Configuration
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

# Advanced Bengali Text Normalization Engine
def normalize_bengali_text(text):
    if not text:
        return ""
    # 1. Unicode NFC Normalization
    text = unicodedata.normalize('NFC', text)
    
    # 2. Fix e-kar (\u09C7) / ai-kar (\u09C8) visual vs logical placement
    text = re.sub(r'\u09C7([\u0985-\u09B9](\u09CD[\u0985-\u09B9])?)', r'\1\u09C7', text)
    text = re.sub(r'\u09C8([\u0985-\u09B9](\u09CD[\u0985-\u09B9])?)', r'\1\u09C8', text)
    
    # 3. Clean zero-width characters and strange spaces
    text = re.sub(r'[\u200B\u200C\u200D]', '', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()

# Multi-Engine PDF Text Extraction
def extract_text_from_pdf_file(file_obj):
    extracted = ""
    # Engine 1: pdfplumber (best for Bengali layout & CMap Unicode)
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
            
    # Engine 2: pypdf (Fallback)
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

    # Engine 3: pdfminer (Fallback)
    if not extracted.strip() and HAS_PDFMINER:
        try:
            file_obj.seek(0)
            extracted = pdfminer_extract(file_obj)
        except Exception:
            pass

    return normalize_bengali_text(extracted)

# Database Auto-Migration & Schema Integrity Guard
def verify_and_migrate_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            description TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id INTEGER,
            name TEXT,
            FOREIGN KEY(exam_id) REFERENCES exams(id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER,
            pyq_year TEXT DEFAULT '',
            is_pyq INTEGER DEFAULT 0,
            question_text TEXT,
            question_text_en TEXT,
            option_a TEXT,
            option_a_en TEXT,
            option_b TEXT,
            option_b_en TEXT,
            option_c TEXT,
            option_c_en TEXT,
            option_d TEXT,
            option_d_en TEXT,
            correct_option CHAR(1),
            explanation TEXT,
            explanation_en TEXT,
            difficulty TEXT DEFAULT 'Medium',
            is_descriptive INTEGER DEFAULT 0,
            marks INTEGER DEFAULT 1,
            model_answer TEXT,
            model_answer_en TEXT,
            marking_scheme TEXT,
            marking_scheme_en TEXT,
            FOREIGN KEY(topic_id) REFERENCES topics(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT DEFAULT 'student',
            full_name TEXT,
            school_name TEXT,
            class_grade TEXT,
            phone TEXT,
            district TEXT,
            approved INTEGER DEFAULT 0,
            is_admin INTEGER DEFAULT 0,
            referral_code TEXT DEFAULT '',
            referral_count INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS student_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT,
            student_phone TEXT,
            school_name TEXT,
            district TEXT,
            exam_name TEXT,
            topic_name TEXT,
            score INTEGER,
            total_questions INTEGER,
            percentage REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS student_doubts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_username TEXT,
            student_name TEXT,
            question_id INTEGER,
            assigned_teacher_username TEXT DEFAULT '',
            teacher_answer TEXT DEFAULT '',
            status TEXT DEFAULT 'Pending',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mock_tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_type TEXT,
            code_num TEXT,
            file_name TEXT,
            file_data BLOB,
            uploader TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    cursor.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('portal_url', 'http://localhost:8501')")

    conn.commit()
    conn.close()

# Run Migration Guard
verify_and_migrate_db()

ADMIN_PASSCODE = "Shawon2026@secure123"

# CSS Styling - High Contrast Theme with Bold Black Text
st.markdown("""
    <style>
    .main {
        background-color: #f1f5f9 !important;
        color: #0f172a !important;
    }
    .stApp {
        font-family: 'SolaimanLipi', 'Kalpurush', 'Noto Sans Bengali', 'Segoe UI', Arial, sans-serif !important;
    }
    .stTextInput input, .stTextArea textarea, .stSelectbox select {
        background-color: #ffffff !important;
        color: #0f172a !important;
        border: 1.5px solid #475569 !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }
    .header-box {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 50%, #0284c7 100%);
        padding: 28px;
        border-radius: 16px;
        color: #ffffff !important;
        text-align: center;
        margin-bottom: 25px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.15);
    }
    .header-box h1 {
        color: #ffffff !important;
        font-size: 2.1rem !important;
        font-weight: 700 !important;
    }
    .card-short {
        background-color: #ffffff !important;
        color: #000000 !important;
        padding: 22px;
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        border-left: 6px solid #2563eb;
        margin-bottom: 18px;
        border-top: 1.5px solid #cbd5e1;
        border-right: 1.5px solid #cbd5e1;
        border-bottom: 1.5px solid #cbd5e1;
    }
    .card-short h4, .card-broad h4 {
        color: #000000 !important;
        font-weight: 900 !important;
        font-size: 1.15rem !important;
    }
    .card-broad {
        background-color: #ffffff !important;
        color: #000000 !important;
        padding: 22px;
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        border-left: 6px solid #7c3aed;
        margin-bottom: 18px;
        border-top: 1.5px solid #cbd5e1;
        border-right: 1.5px solid #cbd5e1;
        border-bottom: 1.5px solid #cbd5e1;
    }
    .footer-block {
        background-color: #0f172a;
        color: #f8fafc;
        padding: 28px;
        border-radius: 14px;
        text-align: center;
        margin-top: 50px;
        border-top: 5px solid #2563eb;
        box-shadow: 0 10px 20px rgba(0,0,0,0.2);
    }
    </style>
""", unsafe_allow_html=True)

# Geography Translation Dictionary
GEO_TRANS_DICT = {
    "বহির্জাত প্রক্রিয়া": "Exogenic Processes",
    "ভূমিরূপ": "Landforms",
    "বায়ুমণ্ডল": "Atmosphere",
    "বারিমণ্ডল": "Hydrosphere",
    "বর্জ্য ব্যবস্থাপনা": "Waste Management",
    "ভারত": "India",
    "উপগ্রহ চিত্র": "Satellite Imagery",
    "ভূ-বৈচিত্র্যসূচক মানচিত্র": "Topographical Maps",
    "পর্যায়ন": "Gradation",
    "বদ্বীপ": "Delta",
    "জলপ্রপাত": "Waterfall",
    "ক্যানিয়ন": "Canyon",
    "মন্থকূপ": "Pot hole"
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

# Geography Question Parser
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
            
            # Auto-detect marks
            m_val = 1
            if re.search(r'([২2]\s*নম্বর|2\s*marks?|[২2]\s*মার্কেল|মান\s*[:\-]?\s*[২2])', line, re.IGNORECASE):
                m_val = 2
            elif re.search(r'([৩3]\s*নম্বর|3\s*marks?|[৩3]\s*মার্কেল|মান\s*[:\-]?\s*[৩3])', line, re.IGNORECASE):
                m_val = 3
            elif re.search(r'([৫5]\s*নম্বর|5\s*marks?|[৫5]\s*মার্কেল|মান\s*[:\-]?\s*[৫5])', line, re.IGNORECASE):
                m_val = 5
                
            current_q = {
                "question": normalize_bengali_text(q_txt),
                "marks": m_val,
                "opt_a": "", "opt_b": "", "opt_c": "", "opt_d": "",
                "correct": "A",
                "explanation": "Extracted from uploaded document.",
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

# Anti-Duplicate Checker
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

# Session State Initialization
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = ""
if 'role' not in st.session_state:
    st.session_state.role = "student"
if 'full_name' not in st.session_state:
    st.session_state.full_name = ""
if 'school_name' not in st.session_state:
    st.session_state.school_name = ""
if 'phone' not in st.session_state:
    st.session_state.phone = ""
if 'district' not in st.session_state:
    st.session_state.district = ""
if 'language' not in st.session_state:
    st.session_state.language = "Bengali"
if 'admin_view_mode' not in st.session_state:
    st.session_state.admin_view_mode = "Admin Control Panel"

# Sidebar Control
st.sidebar.markdown("<h1 style='text-align:center;'>🌍</h1>", unsafe_allow_html=True)
st.sidebar.title("🌍 WBBSE Geo Lab Portal")

# Language Selector
st.session_state.language = st.sidebar.radio("🌐 Language / ভাষা নির্বাচন করুন", ["Bengali", "English"])

# Banner Header
lang = st.session_state.language
if lang == "Bengali":
    st.markdown("""
        <div class="header-box">
            <h1>🌍 পশ্চিমবঙ্গ ভূগোল পরীক্ষা প্রস্তুতি ও ডিজিটাল ল্যাব</h1>
            <p>ওয়েস্ট বেঙ্গল বোর্ড (WBBSE) দশম শ্রেণী অফিশিয়াল ভূগোল সিলেবাস প্র্যাকটিস হাব</p>
        </div>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
        <div class="header-box">
            <h1>🌍 West Bengal Board Geography Portal & Geo Lab</h1>
            <p>Dedicated Practice Platform for WBBSE Class 10 Geography & Environment Syllabus</p>
        </div>
    """, unsafe_allow_html=True)

# LOGIN / REGISTRATION WORKFLOW
if not st.session_state.logged_in:
    tab_login, tab_student_reg, tab_teacher_reg = st.tabs([
        "🔑 Login / লগইন", 
        "🎓 Student Register / ছাত্র-ছাত্রী সাইন-আপ", 
        "👨‍🏫 Teacher Register / শিক্ষক সাইন-আপ"
    ])
    
    with tab_login:
        st.subheader("Sign in to your Account")
        role_select = st.radio("Select Role / ভূমিকা নির্বাচন করুন:", ["Student", "Teacher", "Admin"], horizontal=True)
        login_user = st.text_input("Phone Number or Username / মোবাইল নম্বর বা ইউজারনেম", key="login_u")
        login_pass = st.text_input("Password / পাসওয়ার্ড", type="password", key="login_p")
        
        if st.button("Enter Portal / সাইন-ইন করুন", use_container_width=True):
            if role_select == "Admin" and login_user == "admin" and login_pass == ADMIN_PASSCODE:
                st.session_state.logged_in = True
                st.session_state.username = "admin"
                st.session_state.role = "admin"
                st.session_state.full_name = "Shawon Kar (Head Admin)"
                st.success("Welcome, Head Administrator Shawon Sir!")
                st.rerun()
            else:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT password, role, full_name, school_name, phone, district, approved 
                    FROM users WHERE (username = ? OR phone = ?)
                """, (login_user, login_user))
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
                            st.success(f"Welcome back, {f_name} ({db_role.capitalize()})!")
                            st.rerun()
                        else:
                            st.warning("⚠️ Your account is PENDING approval from Head Admin Shawon Sir. You can log in as soon as approved.")
                    else:
                        st.error("❌ Incorrect Password.")
                else:
                    st.error("❌ Account not found. Please register first.")
                    
    with tab_student_reg:
        st.subheader("New Student Registration / নতুন ছাত্র-ছাত্রী অ্যাকাউন্ট")
        col1, col2 = st.columns(2)
        s_name = col1.text_input("1. Student Name / ছাত্র-ছাত্রীর নাম", key="s_name")
        s_school = col2.text_input("2. School Name / স্কুলের নাম", key="s_sch")
        s_class = col1.selectbox("3. Class / শ্রেণী", ["Class 10 (Madhyamik)"])
        s_phone = col2.text_input("4. Phone Number / মোবাইল নম্বর", key="s_ph")
        s_dist = col1.text_input("5. District / জেলা", key="s_dist")
        s_pass = col2.text_input("6. Set Password / পাসওয়ার্ড দিন", type="password", key="s_pass")
        ref_input = st.text_input("7. Referral Code (Optional) / রেফারাল কোড", key="s_ref")
        
        if st.button("Submit Student Registration", use_container_width=True):
            if s_name and s_school and s_phone and s_pass:
                try:
                    conn = get_connection()
                    cursor = conn.cursor()
                    auto_ref = f"GEO-REF-{s_phone[-4:] if len(s_phone)>=4 else '10'}"
                    cursor.execute("""
                        INSERT INTO users (username, password, role, full_name, school_name, class_grade, phone, district, approved, is_admin, referral_code)
                        VALUES (?, ?, 'student', ?, ?, ?, ?, ?, 0, 0, ?)
                    """, (s_phone, s_pass, s_name, s_school, s_class, s_phone, s_dist, auto_ref))
                    
                    if ref_input.strip():
                        cursor.execute("UPDATE users SET referral_count = referral_count + 1 WHERE referral_code = ?", (ref_input.strip(),))
                        
                    conn.commit()
                    conn.close()
                    st.success("🎉 Registration requested successfully! As soon as Shawon Sir approves, you can log in.")
                except sqlite3.IntegrityError:
                    st.error("❌ An account with this phone number already exists.")
            else:
                st.error("⚠️ Please fill in required fields.")
                
    with tab_teacher_reg:
        st.subheader("New Teacher Registration / নতুন শিক্ষক অ্যাকাউন্ট")
        col1, col2 = st.columns(2)
        t_name = col1.text_input("1. Teacher Name / শিক্ষকের নাম", key="t_name")
        t_school = col2.text_input("2. School Name / স্কুলের নাম", key="t_sch")
        t_phone = col1.text_input("3. Phone Number / মোবাইল নম্বর", key="t_ph")
        t_dist = col2.text_input("4. District / জেলা", key="t_dist")
        t_pass = col1.text_input("5. Set Password / পাসওয়ার্ড দিন", type="password", key="t_pass")
        t_ref_in = st.text_input("6. Referral Code (Optional)", key="t_ref")
        
        if st.button("Submit Teacher Registration", use_container_width=True):
            if t_name and t_school and t_phone and t_pass:
                try:
                    conn = get_connection()
                    cursor = conn.cursor()
                    auto_t_ref = f"GEO-REF-T{t_phone[-4:] if len(t_phone)>=4 else '99'}"
                    cursor.execute("""
                        INSERT INTO users (username, password, role, full_name, school_name, class_grade, phone, district, approved, is_admin, referral_code)
                        VALUES (?, ?, 'teacher', ?, ?, 'Faculty', ?, ?, 0, 0, ?)
                    """, (t_phone, t_pass, t_name, t_school, t_phone, t_dist, auto_t_ref))
                    
                    if t_ref_in.strip():
                        cursor.execute("UPDATE users SET referral_count = referral_count + 1 WHERE referral_code = ?", (t_ref_in.strip(),))
                        
                    conn.commit()
                    conn.close()
                    st.success("🎉 Teacher registration requested! Upon admin approval, you can log in.")
                except sqlite3.IntegrityError:
                    st.error("❌ An account with this phone number already exists.")
            else:
                st.error("⚠️ Please fill in required fields.")

else:
    # LOGGED IN USER INTERFACE
    st.sidebar.markdown(f"👤 **Name:** `{st.session_state.full_name}`")
    st.sidebar.markdown(f"🎭 **Role:** `{st.session_state.role.capitalize()}`")
    if st.session_state.school_name:
        st.sidebar.caption(f"🏫 {st.session_state.school_name} | {st.session_state.district}")
        
    if st.session_state.role == "admin":
        st.sidebar.markdown("---")
        st.sidebar.markdown("👑 **Admin Super-Control**")
        st.session_state.admin_view_mode = st.sidebar.radio("View Portal As:", ["Admin Control Panel", "Teacher View", "Student View"])
        
    if st.sidebar.button("Logout / লগআউট"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.role = "student"
        st.session_state.full_name = ""
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

    # Navigation Options
    if active_view_role == "student":
        st_nav = st.sidebar.selectbox("🎯 Navigation Menu", [
            "📖 Practice Center", 
            "❓ My Help / Doubt Requests",
            "📄 Sequential Mock Tests & Suggestions",
            "📁 Madhyamik Drive Papers",
            "🎁 Share & Referral Links"
        ])
    elif active_view_role == "teacher":
        st_nav = st.sidebar.selectbox("🎯 Navigation Menu", [
            "📥 Assigned Student Doubts",
            "📖 Question Bank Manager", 
            "📄 Upload Sequential Mock Tests & Suggestions",
            "👨‍🏫 Geo Lab Student Track Records",
            "📁 Madhyamik Drive Papers",
            "🎁 Share & Referral Links"
        ])
    else: # admin
        st_nav = st.sidebar.selectbox("🎯 Navigation Menu", [
            "🛡️ User Approvals", 
            "❓ Student Doubt Assignment Hub",
            "📖 Question Bank Manager", 
            "📄 Upload Sequential Mock Tests & Suggestions",
            "📁 Madhyamik Drive Papers",
            "📊 Analytics & Track Records",
            "🎁 Share & Referral Links"
        ])

    # SHARED FEATURE: MADHYAMIK DRIVE PAPERS LINK
    if st_nav == "📁 Madhyamik Drive Papers":
        st.subheader("📁 Official Madhyamik Secondary Examination Google Drive Papers")
        st.markdown("""
            <div style="background-color: #eff6ff; border: 2px solid #2563eb; padding: 22px; border-radius: 12px; margin-bottom: 20px;">
                <h3 style="color: #1e3a8a; margin-top:0;">📥 Official Madhyamik Board Question Papers Collection</h3>
                <p>Access past years official Madhyamik Geography question papers directly from our cloud storage drive:</p>
                <a href="https://drive.google.com/drive/folders/1q4cLE5sYcjElqSnZPQ4Tx4lkbrB-U-pj?usp=drive_link" target="_blank" style="background-color: #2563eb; color: white; padding: 10px 20px; border-radius: 8px; text-decoration: none; font-weight: bold; display: inline-block;">🔗 Open Official Madhyamik Google Drive Folder</a>
            </div>
        """, unsafe_allow_html=True)
        
        st.markdown("### 📋 Instructions for Students / শিক্ষার্থীদের জন্য নির্দেশিকা:")
        st.markdown("""
            ১. **লিংকে ক্লিক করুন:** উপরের **'Open Official Madhyamik Google Drive Folder'** বোতামে চাপ দিলে নতুন ট্যাবে ড্রাইভের ফোল্ডার খুলে যাবে।
            ২. **প্রশ্নপত্র পছন্দ করুন:** ড্রাইভে ২০১৭ থেকে ২০২৬ সালের মাধ্যমিক পরীক্ষার অফিশিয়াল ভূগোল প্রশ্নপত্র ফাইল দেখতে পাবেন।
            ৩. **অনলাইনে পঠন ও ডাউনলোড:** ডাবল-ক্লিক করে ড্রাইভে পড়তে পারবেন এবং ডাউনলোডে চাপ দিলে সরাসরি ফোনে বা কম্পিউটারে ফাইল সেভ হয়ে যাবে।
        """)

    # SHARED FEATURE: SHARE & REFERRAL LINKS
    elif st_nav == "🎁 Share & Referral Links":
        st.subheader("🎁 Refer Friends & Share Geo Portal / বন্ধুদের শেয়ার করুন")
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT referral_code, referral_count FROM users WHERE username = ?", (st.session_state.username,))
        ref_row = cursor.fetchone()
        
        cursor.execute("SELECT value FROM system_settings WHERE key = 'portal_url'")
        url_row = cursor.fetchone()
        current_portal_url = url_row[0] if url_row else "http://localhost:8501"
        
        my_code = ref_row[0] if ref_row and ref_row[0] else "GEO-REF-10"
        my_count = ref_row[1] if ref_row and ref_row[1] else 0
        
        if role == "admin":
            st.markdown("#### 🌐 Portal Web Link Configuration")
            new_url_val = st.text_input("Set Official Web Link for Referral Sharing:", value=current_portal_url)
            if st.button("💾 Save Portal URL"):
                cursor.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('portal_url', ?)", (new_url_val.strip(),))
                conn.commit()
                current_portal_url = new_url_val.strip()
                st.success("Updated Portal URL!")
                st.rerun()
                
        conn.close()
        
        col1, col2 = st.columns(2)
        col1.metric("Your Unique Referral Code", my_code)
        col2.metric("Successful Referrals Completed", f"{my_count} / 100")
        
        st.progress(min(my_count / 100.0, 1.0))
        
        if my_count >= 100:
            st.balloons()
            st.success("🎉 CONGRATULATIONS! You have completed 100 referrals! Special Geo Lab Award Certificate Unlocked!")
            st.button("📥 Download Your Award Certificate (PDF)")
        else:
            st.info(f"💡 Complete {100 - my_count} more successful referrals to unlock your Special Geography Award Certificate!")

        st.markdown("### 📲 Direct Share Links for Phone & Social Media:")
        
        share_msg = f"Join WBBSE Class 10 Geography Portal! Access practice sets, 10-Yr PYQs & mock tests.\n🌐 Portal Link: {current_portal_url}\n🔑 Referral Code: {my_code}\nUse my code during sign-up to unlock practice sets!"
        encoded_msg = urllib.parse.quote(share_msg)
        
        col_wa, col_sms, col_fb = st.columns(3)
        col_wa.markdown(f'<a href="https://api.whatsapp.com/send?text={encoded_msg}" target="_blank" style="background-color:#22c55e; color:white; padding:10px 16px; border-radius:8px; text-decoration:none; font-weight:bold; display:block; text-align:center;">📱 Share via WhatsApp</a>', unsafe_allow_html=True)
        col_sms.markdown(f'<a href="sms:?body={encoded_msg}" style="background-color:#0284c7; color:white; padding:10px 16px; border-radius:8px; text-decoration:none; font-weight:bold; display:block; text-align:center;">💬 Share via Text SMS</a>', unsafe_allow_html=True)
        col_fb.markdown(f'<a href="https://www.facebook.com/sharer/sharer.php?u={urllib.parse.quote(current_portal_url)}&quote={encoded_msg}" target="_blank" style="background-color:#1d4ed8; color:white; padding:10px 16px; border-radius:8px; text-decoration:none; font-weight:bold; display:block; text-align:center;">📘 Share on Facebook</a>', unsafe_allow_html=True)

        st.markdown("#### 📋 Copy Full Share Text & Link:")
        st.text_area("Share Text:", value=share_msg, height=120)

    # -------------------------------------------------------------
    # STUDENT PORTAL VIEW
    # -------------------------------------------------------------
    elif active_view_role == "student":
        if st_nav == "📖 Practice Center":
            st.subheader("📖 WBBSE Class 10 Geography Practice Center")
            
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, name FROM topics ORDER BY id ASC")
            c10_topics = cursor.fetchall()
            topic_dict = {t[1]: t[0] for t in c10_topics}
            
            selected_topic_name = st.selectbox("Select Class 10 Chapter / অধ্যায় নির্বাচন করুন:", list(topic_dict.keys()))
            target_t_id = topic_dict[selected_topic_name]
            
            cursor.execute("""
                SELECT id, question_text, question_text_en, option_a, option_a_en, option_b, option_b_en,
                       option_c, option_c_en, option_d, option_d_en, correct_option, explanation, explanation_en,
                       difficulty, is_descriptive, marks, model_answer, model_answer_en, marking_scheme, marking_scheme_en
                FROM questions WHERE topic_id = ?
            """, (target_t_id,))
            all_questions = cursor.fetchall()
            conn.close()
            
            if not all_questions:
                st.info("No questions added under this chapter yet. Upload some in Question Bank Manager!")
            else:
                q1_list = [q for q in all_questions if q[16] == 1]
                q2_list = [q for q in all_questions if q[16] == 2]
                q3_list = [q for q in all_questions if q[16] == 3]
                q5_list = [q for q in all_questions if q[16] == 5 or q[16] > 3]
                
                t1, t2, t3, t5 = st.tabs([
                    f"📁 1 Mark Questions ({len(q1_list)})",
                    f"📁 2 Marks Questions ({len(q2_list)})",
                    f"📁 3 Marks Questions ({len(q3_list)})",
                    f"📁 5 Marks Broad Questions ({len(q5_list)})"
                ])
                
                # Helper function for rendering 2, 3, 5 marks questions
                def render_broad_question_set(q_list, mark_label):
                    if not q_list:
                        st.info(f"No {mark_label} questions loaded in this chapter.")
                        return
                    for idx, q in enumerate(q_list, 1):
                        q_id, q_bn, q_en, oa_bn, oa_en, ob_bn, ob_en, oc_bn, oc_en, od_bn, od_en, corr_opt, expl_bn, expl_en, diff, is_desc, m_val, m_ans_bn, m_ans_en, ms_bn, ms_en = q
                        q_label = (q_bn if lang == "Bengali" else q_en) or translate_geo_term(q_bn, lang)
                        
                        st.markdown(f"""
                            <div class="card-broad">
                                <span style="background-color: #7c3aed; color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; float: right;">{m_val} Marks ({mark_label})</span>
                                <h4>Q{idx}. {q_label}</h4>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        # Check doubt status
                        conn = get_connection()
                        cursor = conn.cursor()
                        cursor.execute("SELECT status, teacher_answer FROM student_doubts WHERE student_username = ? AND question_id = ?", (st.session_state.username, q_id))
                        d_row = cursor.fetchone()
                        conn.close()
                        
                        if d_row and d_row[0] in ["Approved", "Resolved by Teacher (Pending Approval)"] and d_row[1].strip():
                            st.success(f"✅ Solution Unlocked! Status: {d_row[0]}")
                            st.markdown(f"**Model Answer / সমাধান:**\n{d_row[1]}")
                            st.download_button("📥 Download Solution (.txt)", data=d_row[1], file_name=f"Solution_Q{q_id}.txt", key=f"dl_sol_{q_id}")
                        else:
                            st.caption("🔒 Model Answer is hidden by default.")
                            col_req1, col_req2 = st.columns([2, 3])
                            if col_req1.button(f"🙋 Ask Admin / Request Solution for Q{idx}", key=f"req_btn_{q_id}"):
                                conn = get_connection()
                                cursor = conn.cursor()
                                cursor.execute("""
                                    INSERT INTO student_doubts (student_username, student_name, question_id, status)
                                    VALUES (?, ?, ?, 'Pending Admin Assignment')
                                """, (st.session_state.username, st.session_state.full_name, q_id))
                                conn.commit()
                                conn.close()
                                st.success("🎉 Doubt request sent to Admin & Teachers! Solution will be unlocked once resolved.")
                                st.rerun()
                        st.markdown("<hr/>", unsafe_allow_html=True)

                with t1:
                    if not q1_list:
                        st.info("No 1-mark questions loaded in this chapter.")
                    else:
                        for idx, q in enumerate(q1_list, 1):
                            q_id, q_bn, q_en, oa_bn, oa_en, ob_bn, ob_en, oc_bn, oc_en, od_bn, od_en, corr_opt, expl_bn, expl_en, diff, is_desc, m_val, m_ans_bn, m_ans_en, ms_bn, ms_en = q
                            q_label = (q_bn if lang == "Bengali" else q_en) or translate_geo_term(q_bn, lang)
                            
                            st.markdown(f"""
                                <div class="card-short">
                                    <span style="background-color: #2563eb; color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; float: right;">1 Mark (Short)</span>
                                    <h4>Q{idx}. {q_label}</h4>
                                </div>
                            """, unsafe_allow_html=True)
                            
                            if oa_bn or oa_en:
                                opts = [
                                    f"A) {(oa_bn if lang == 'Bengali' else oa_en) or translate_geo_term(oa_bn, lang)}",
                                    f"B) {(ob_bn if lang == 'Bengali' else ob_en) or translate_geo_term(ob_bn, lang)}",
                                    f"C) {(oc_bn if lang == 'Bengali' else oc_en) or translate_geo_term(oc_bn, lang)}",
                                    f"D) {(od_bn if lang == 'Bengali' else od_en) or translate_geo_term(od_bn, lang)}"
                                ]
                                user_ans = st.radio(f"Select Option for Q{idx}:", opts, index=None, key=f"std_mcq_{q_id}")
                                if user_ans:
                                    if user_ans[0] == corr_opt:
                                        st.success(f"✅ Correct! Answer: Option {corr_opt}")
                                    else:
                                        st.error(f"❌ Incorrect. Correct Option is {corr_opt}")
                                    st.info(f"💡 **Explanation:** {(expl_bn if lang == 'Bengali' else expl_en) or translate_geo_term(expl_bn, lang)}")
                            else:
                                with st.expander("👁️ View SAQ Correct Answer & Explanation"):
                                    st.markdown(f"**Correct Answer:** {corr_opt}")
                                    st.markdown(f"**Explanation:** {(expl_bn if lang == 'Bengali' else expl_en) or translate_geo_term(expl_bn, lang)}")
                            st.markdown("<hr/>", unsafe_allow_html=True)

                with t2:
                    render_broad_question_set(q2_list, "2 Marks")
                with t3:
                    render_broad_question_set(q3_list, "3 Marks")
                with t5:
                    render_broad_question_set(q5_list, "5 Marks Broad")

        elif st_nav == "❓ My Help / Doubt Requests":
            st.subheader("❓ My Doubt Requests & Unlocked Solutions")
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT d.id, q.question_text, q.marks, d.status, d.teacher_answer, d.timestamp
                FROM student_doubts d JOIN questions q ON d.question_id = q.id
                WHERE d.student_username = ? ORDER BY d.id DESC
            """, (st.session_state.username,))
            my_doubts = cursor.fetchall()
            conn.close()
            
            if not my_doubts:
                st.info("You haven't requested any doubt solutions yet. Click 'Ask Admin' on any 2, 3, or 5 marks question in Practice Center!")
            else:
                for d_id, q_txt, q_m, status, t_ans, t_stamp in my_doubts:
                    with st.expander(f"📌 Doubt ID #{d_id} [{q_m} Marks] - Status: {status} ({t_stamp})"):
                        st.markdown(f"**Question:** {q_txt}")
                        if t_ans and t_ans.strip():
                            st.success(f"✅ Solution Approved!\n\n{t_ans}")
                            st.download_button("📥 Download Solution Text", data=t_ans, file_name=f"Doubt_Solution_{d_id}.txt", key=f"my_dl_{d_id}")
                        else:
                            st.info("⏳ Pending resolution by Admin or Assigned Teacher.")

        elif st_nav == "📄 Sequential Mock Tests & Suggestions":
            st.subheader("📄 Sequential Mock Tests & Suggestions Portal")
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, test_type, code_num, file_name, file_data, uploader, timestamp FROM mock_tests ORDER BY id DESC")
            mocks = cursor.fetchall()
            conn.close()
            
            if not mocks:
                st.info("No mock tests or suggestions uploaded yet.")
            else:
                for m_id, t_type, c_num, f_name, f_data, uploader, t_stamp in mocks:
                    st.markdown(f"### 📄 `{c_num}` - {t_type} ({f_name})")
                    st.caption(f"Uploaded by: {uploader} | Date: {t_stamp}")
                    if f_data:
                        st.download_button(f"📥 Download {c_num} Paper", data=f_data, file_name=f_name, key=f"dl_mock_{m_id}")
                    st.markdown("---")

    # -------------------------------------------------------------
    # TEACHER PORTAL VIEW
    # -------------------------------------------------------------
    elif active_view_role == "teacher":
        if st_nav == "📥 Assigned Student Doubts":
            st.subheader("📥 Student Doubts Assigned to You")
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT d.id, d.student_name, q.question_text, q.marks, d.status, d.teacher_answer 
                FROM student_doubts d JOIN questions q ON d.question_id = q.id
                WHERE d.assigned_teacher_username = ?
                ORDER BY d.id DESC
            """, (st.session_state.username,))
            my_doubts = cursor.fetchall()
            conn.close()
            
            if not my_doubts:
                st.info("No doubts currently assigned to you by Admin.")
            else:
                for d_id, s_name, q_txt, q_m, status, t_ans in my_doubts:
                    with st.expander(f"📌 Doubt ID #{d_id} [{q_m} Marks] - Student: {s_name} (Status: {status})"):
                        st.markdown(f"**Question:** {q_txt}")
                        sol_in = st.text_area(f"Write Solution for Doubt #{d_id}:", value=t_ans, key=f"t_sol_{d_id}")
                        if st.button(f"Submit Solution to Admin for Doubt #{d_id}", key=f"t_btn_{d_id}"):
                            conn = get_connection()
                            cursor = conn.cursor()
                            cursor.execute("UPDATE student_doubts SET teacher_answer = ?, status = 'Resolved by Teacher (Pending Approval)' WHERE id = ?", (sol_in.strip(), d_id))
                            conn.commit()
                            conn.close()
                            st.success("🎉 Submitted to Admin! Admin will review and approve your answer.")
                            st.rerun()

        elif st_nav == "📖 Question Bank Manager":
            st.subheader("📖 Question Bank Manager & File/URL Auto-Extractor")
            
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, name FROM topics ORDER BY id ASC")
            c10_topics = cursor.fetchall()
            topic_dict = {t[1]: t[0] for t in c10_topics}
            conn.close()
            
            sel_topic_name = st.selectbox("Target Class 10 Chapter:", list(topic_dict.keys()), key="man_top_sel")
            target_t_id = topic_dict[sel_topic_name]
            
            tab_ext, tab_man, tab_del = st.tabs([
                "⚡ File / URL Question Extractor",
                "➕ Manual Single Question Upload",
                "📖 Browse & Delete Questions"
            ])
            
            with tab_ext:
                st.markdown("### 📤 Question Corner Auto-Extract Engine (PDF / DOCX / URL)")
                st.info("Upload PDF/DOCX question papers or paste a Website URL link. The system extracts text, normalizes Bengali fonts, and categorizes questions into 1, 2, 3, and 5 marks folders automatically!")
                
                source_type = st.radio("Select Extraction Source:", ["PDF / DOCX File Upload", "Website Page Link (URL)"], horizontal=True)
                
                extracted_text = ""
                if source_type == "PDF / DOCX File Upload":
                    file_obj = st.file_uploader("Upload Question File (.pdf or .docx)", type=["pdf", "docx"], key="upl_ext_file")
                    if file_obj is not None:
                        ext = file_obj.name.split('.')[-1].lower()
                        if ext == "pdf":
                            extracted_text = extract_text_from_pdf_file(file_obj)
                        elif ext == "docx" and HAS_DOCX:
                            doc_file = docx.Document(file_obj)
                            raw_txt = "\n".join([para.text for para in doc_file.paragraphs if para.text.strip()])
                            extracted_text = normalize_bengali_text(raw_txt)
                else:
                    web_url = st.text_input("Paste Web Page URL Link:", key="web_url_input")
                    if st.button("🌐 Fetch Content from Web URL"):
                        if web_url.strip():
                            try:
                                req = urllib.request.Request(web_url.strip(), headers={'User-Agent': 'Mozilla/5.0'})
                                with urllib.request.urlopen(req, timeout=10) as resp:
                                    html_text = resp.read().decode('utf-8', errors='ignore')
                                    raw_text = re.sub(r'<[^>]+>', ' ', html_text)
                                    extracted_text = normalize_bengali_text(raw_text)
                                    st.success("Fetched and normalized web page content successfully!")
                            except Exception as e:
                                st.error(f"Error fetching URL: {e}")

                if extracted_text:
                    st.markdown("#### 📝 Normalized Extracted Text Preview (Editable):")
                    edited_extracted_text = st.text_area("Review Extracted Bengali Text:", value=extracted_text, height=220, key="edit_ext_txt")
                    
                    parsed_candidates = parse_and_categorize_questions(edited_extracted_text)
                    st.success(f"Extracted {len(parsed_candidates)} candidate questions!")
                    
                    m1_qs = [q for q in parsed_candidates if q["marks"] == 1]
                    m2_qs = [q for q in parsed_candidates if q["marks"] == 2]
                    m3_qs = [q for q in parsed_candidates if q["marks"] == 3]
                    m5_qs = [q for q in parsed_candidates if q["marks"] == 5]
                    
                    f1, f2, f3, f5 = st.tabs([
                        f"📁 1 Mark ({len(m1_qs)})",
                        f"📁 2 Marks ({len(m2_qs)})",
                        f"📁 3 Marks ({len(m3_qs)})",
                        f"📁 5 Marks ({len(m5_qs)})"
                    ])
                    
                    with f1:
                        if m1_qs: st.dataframe(pd.DataFrame(m1_qs), use_container_width=True)
                    with f2:
                        if m2_qs: st.dataframe(pd.DataFrame(m2_qs), use_container_width=True)
                    with f3:
                        if m3_qs: st.dataframe(pd.DataFrame(m3_qs), use_container_width=True)
                    with f5:
                        if m5_qs: st.dataframe(pd.DataFrame(m5_qs), use_container_width=True)

                    if st.button("🚀 Save All Categorized Questions to Database", use_container_width=True):
                        conn = get_connection()
                        cursor = conn.cursor()
                        saved_count = 0
                        for q_item in parsed_candidates:
                            q_bn = q_item["question"]
                            q_en = translate_geo_term(q_bn, "English")
                            cursor.execute("""
                                INSERT INTO questions (
                                    topic_id, question_text, question_text_en,
                                    option_a, option_b, option_c, option_d,
                                    correct_option, explanation, difficulty, is_descriptive, marks,
                                    model_answer, marking_scheme
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Medium', ?, ?, ?, ?)
                            """, (
                                target_t_id, q_bn, q_en,
                                q_item["opt_a"], q_item["opt_b"], q_item["opt_c"], q_item["opt_d"],
                                q_item["correct"], q_item["explanation"],
                                q_item["is_descriptive"], q_item["marks"],
                                q_bn if q_item["is_descriptive"] else "",
                                f"{q_item['marks']} Marks Evaluation Scheme"
                            ))
                            saved_count += 1
                        conn.commit()
                        conn.close()
                        st.success(f"🎉 Successfully saved {saved_count} categorized questions into Chapter `{sel_topic_name}`!")
                        st.rerun()

            with tab_man:
                st.markdown("### ➕ Manual Question Upload with Anti-Duplicate Intelligence")
                q_text_bn = st.text_area("Question Text (Bengali / Avro):", key="man_q_bn")
                q_marks = st.selectbox("Select Marks:", [1, 2, 3, 5], key="man_q_marks")
                
                if q_text_bn.strip():
                    match, ratio = check_duplicate_question(q_text_bn, target_t_id)
                    if match:
                        st.warning(f"⚠️ Duplicate Question Warning! ({ratio*100:.1f}% match in DB):")
                        st.caption(f"Existing Q_ID #{match[0]}: {match[1]}")

                if q_marks == 1:
                    col1, col2 = st.columns(2)
                    oa_bn = col1.text_input("Option A (Bengali/Avro):")
                    ob_bn = col2.text_input("Option B (Bengali/Avro):")
                    oc_bn = col1.text_input("Option C (Bengali/Avro):")
                    od_bn = col2.text_input("Option D (Bengali/Avro):")
                    corr_opt = st.selectbox("Correct Option:", ["A", "B", "C", "D"])
                    expl_bn = st.text_area("Explanation:")
                    
                    if st.button("Save 1 Mark MCQ to DB", use_container_width=True):
                        if q_text_bn and oa_bn:
                            conn = get_connection()
                            cursor = conn.cursor()
                            q_en = translate_geo_term(q_text_bn, "English")
                            cursor.execute("""
                                INSERT INTO questions (
                                    topic_id, question_text, question_text_en,
                                    option_a, option_b, option_c, option_d,
                                    correct_option, explanation, difficulty, is_descriptive, marks
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Medium', 0, 1)
                            """, (target_t_id, q_text_bn, q_en, oa_bn, ob_bn, oc_bn, od_bn, corr_opt, expl_bn))
                            conn.commit()
                            conn.close()
                            st.success("🎉 Added 1 mark question!")
                            st.rerun()
                else:
                    m_ans_bn = st.text_area(f"Model Answer for {q_marks} Marks:")
                    m_sch_bn = st.text_area("Marking Scheme:")
                    if st.button(f"Save {q_marks} Marks Broad Question to DB", use_container_width=True):
                        if q_text_bn:
                            conn = get_connection()
                            cursor = conn.cursor()
                            q_en = translate_geo_term(q_text_bn, "English")
                            cursor.execute("""
                                INSERT INTO questions (
                                    topic_id, question_text, question_text_en,
                                    difficulty, is_descriptive, marks, model_answer, marking_scheme
                                ) VALUES (?, ?, ?, 'Hard', 1, ?, ?, ?)
                            """, (target_t_id, q_text_bn, q_en, q_marks, m_ans_bn, m_sch_bn))
                            conn.commit()
                            conn.close()
                            st.success(f"🎉 Added {q_marks} marks question!")
                            st.rerun()

            with tab_del:
                st.markdown("### 📖 Browse & Direct Question Delete Engine")
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id, question_text, marks, is_descriptive FROM questions WHERE topic_id = ? ORDER BY id DESC", (target_t_id,))
                q_rows = cursor.fetchall()
                conn.close()
                
                if not q_rows:
                    st.info("No questions stored in this chapter yet.")
                else:
                    for q_id, q_txt, q_m, is_d in q_rows:
                        col_q1, col_q2 = st.columns([5, 1])
                        col_q1.markdown(f"**Q_ID #{q_id} [{q_m} Marks]:** {q_txt}")
                        if col_q2.button(f"🗑️ Delete #{q_id}", key=f"del_q_{q_id}"):
                            conn = get_connection()
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM questions WHERE id = ?", (q_id,))
                            conn.commit()
                            conn.close()
                            st.success(f"Deleted Question #{q_id}!")
                            st.rerun()

        elif st_nav == "📄 Upload Sequential Mock Tests & Suggestions":
            st.subheader("📄 Upload Sequential Mock Tests & Suggestions (PDF / DOCX)")
            
            t_type = st.radio("Select Test Type:", ["Chapter Wise Mock Test", "Final Mock Test", "Board Suggestions"], horizontal=True)
            
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM mock_tests WHERE test_type = ?", (t_type,))
            existing_cnt = cursor.fetchone()[0]
            conn.close()
            
            prefix = "chapter mock" if t_type == "Chapter Wise Mock Test" else ("final mock test" if t_type == "Final Mock Test" else "suggestion")
            auto_code = f"{prefix} - {existing_cnt + 1:03d}"
            
            st.info(f"Generated File Code: `{auto_code}`")
            up_file = st.file_uploader("Choose File (.pdf or .docx)", type=["pdf", "docx"], key="mock_up_file")
            
            if st.button("🚀 Publish Mock Test / Suggestion Paper", use_container_width=True):
                if up_file is not None:
                    f_bytes = up_file.getvalue()
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO mock_tests (test_type, code_num, file_name, file_data, uploader)
                        VALUES (?, ?, ?, ?, ?)
                    """, (t_type, auto_code, up_file.name, f_bytes, st.session_state.full_name))
                    conn.commit()
                    conn.close()
                    st.success(f"🎉 Published `{auto_code}` successfully!")
                    st.rerun()

        elif st_nav == "👨‍🏫 Geo Lab Student Track Records":
            st.subheader("👨‍🏫 Geo Lab Student Track Records")
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT student_name, student_phone, school_name, district, exam_name, topic_name, score, total_questions, percentage, timestamp
                FROM student_scores ORDER BY timestamp DESC
            """)
            scores = cursor.fetchall()
            conn.close()
            
            if not scores:
                st.info("No student test records recorded yet.")
            else:
                df_scores = pd.DataFrame(scores, columns=["Student Name", "Phone", "School", "District", "Standard", "Topic", "Score", "Total Qs", "Percentage (%)", "Timestamp"])
                st.dataframe(df_scores, use_container_width=True)

    # -------------------------------------------------------------
    # ADMIN PORTAL VIEW
    # -------------------------------------------------------------
    elif active_view_role == "admin":
        if st_nav == "🛡️ User Approvals":
            st.subheader("🛡️ Head Admin User Approvals")
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, role, full_name, school_name, class_grade, phone, district, approved 
                FROM users WHERE is_admin = 0 ORDER BY approved ASC, id DESC
            """)
            all_u = cursor.fetchall()
            conn.close()
            
            if not all_u:
                st.info("No registered user accounts.")
            else:
                df_u = pd.DataFrame(all_u, columns=["User ID", "Role", "Name", "School", "Class", "Phone", "District", "Approval State"])
                st.dataframe(df_u, use_container_width=True)
                
                sel_uid = st.number_input("Enter User ID to Update Approval:", min_value=1, step=1)
                col1, col2 = st.columns(2)
                if col1.button("✅ Approve Account", use_container_width=True):
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute("UPDATE users SET approved = 1 WHERE id = ?", (sel_uid,))
                    conn.commit()
                    conn.close()
                    st.success(f"Approved User ID #{sel_uid}!")
                    st.rerun()
                if col2.button("🚫 Revoke Account", use_container_width=True):
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute("UPDATE users SET approved = 0 WHERE id = ?", (sel_uid,))
                    conn.commit()
                    conn.close()
                    st.warning(f"Revoked User ID #{sel_uid}!")
                    st.rerun()

        elif st_nav == "❓ Student Doubt Assignment Hub":
            st.subheader("❓ Student Doubt Assignment & Solution Review Hub")
            
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT d.id, d.student_name, q.question_text, q.marks, d.assigned_teacher_username, d.teacher_answer, d.status, d.question_id
                FROM student_doubts d JOIN questions q ON d.question_id = q.id
                ORDER BY d.id DESC
            """)
            doubts = cursor.fetchall()
            
            cursor.execute("SELECT username, full_name FROM users WHERE role = 'teacher' AND approved = 1")
            teachers = cursor.fetchall()
            teacher_map = {f"{t[1]} ({t[0]})": t[0] for t in teachers}
            conn.close()
            
            if not doubts:
                st.info("No active student doubt requests.")
            else:
                df_d = pd.DataFrame(doubts, columns=["Doubt ID", "Student Name", "Question", "Marks", "Assigned Teacher", "Teacher Solution", "Status", "Q_ID"])
                st.dataframe(df_d[["Doubt ID", "Student Name", "Question", "Marks", "Assigned Teacher", "Teacher Solution", "Status"]], use_container_width=True)
                
                sel_d_id = st.number_input("Select Doubt ID to Review, Assign, or Approve:", min_value=1, step=1, key="adm_rev_did")
                
                # Fetch selected doubt details
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT d.id, d.student_name, q.question_text, q.marks, d.assigned_teacher_username, d.teacher_answer, d.status
                    FROM student_doubts d JOIN questions q ON d.question_id = q.id
                    WHERE d.id = ?
                """, (sel_d_id,))
                sel_doubt_row = cursor.fetchone()
                conn.close()
                
                if sel_doubt_row:
                    d_id, s_name, q_txt, q_m, t_user, t_ans, d_stat = sel_doubt_row
                    st.markdown(f"### 📌 Selected Doubt ID #{d_id} [{q_m} Marks]")
                    st.markdown(f"**Student:** {s_name} | **Current Status:** `{d_stat}`")
                    st.markdown(f"**Question:** {q_txt}")
                    
                    # TEACHER SUBMITTED SOLUTION REVIEW BOX
                    if t_ans and t_ans.strip():
                        st.markdown("#### 📩 Teacher Submitted Solution for Review:")
                        rev_ans_text = st.text_area("Review & Edit Teacher Answer before Approval:", value=t_ans, height=150, key=f"rev_ta_{d_id}")
                        if st.button("✅ Approve Teacher Answer & Unlock for Student", use_container_width=True):
                            conn = get_connection()
                            cursor = conn.cursor()
                            cursor.execute("UPDATE student_doubts SET teacher_answer = ?, status = 'Approved' WHERE id = ?", (rev_ans_text.strip(), d_id))
                            conn.commit()
                            conn.close()
                            st.success("🎉 Teacher Answer APPROVED & Unlocked for Student! Status updated to Approved.")
                            st.rerun()
                    else:
                        st.caption("No teacher answer submitted for this doubt yet.")
                    
                    st.markdown("---")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.markdown("#### Option 1: Assign to Teacher")
                        if teacher_map:
                            sel_t_lbl = st.selectbox("Select Teacher:", list(teacher_map.keys()), key="adm_assign_t")
                            sel_t_usr = teacher_map[sel_t_lbl]
                            if st.button("Assign Doubt to Teacher"):
                                conn = get_connection()
                                cursor = conn.cursor()
                                cursor.execute("UPDATE student_doubts SET assigned_teacher_username = ?, status = 'Assigned to Teacher' WHERE id = ?", (sel_t_usr, d_id))
                                conn.commit()
                                conn.close()
                                st.success(f"Assigned Doubt #{d_id} to teacher!")
                                st.rerun()
                        else:
                            st.caption("No approved teachers available.")
                    with col_b:
                        st.markdown("#### Option 2: Solve Directly as Admin")
                        adm_direct_sol = st.text_area("Write Admin Solution / Model Answer:", key="adm_dir_sol")
                        if st.button("Approve Admin Solution & Unlock for Student"):
                            if adm_direct_sol.strip():
                                conn = get_connection()
                                cursor = conn.cursor()
                                cursor.execute("UPDATE student_doubts SET teacher_answer = ?, status = 'Approved' WHERE id = ?", (adm_direct_sol.strip(), d_id))
                                conn.commit()
                                conn.close()
                                st.success(f"Admin Solution Approved for Doubt #{d_id}!")
                                st.rerun()

        elif st_nav == "📖 Question Bank Manager":
            st.subheader("📖 Question Bank Manager & File/URL Auto-Extractor")
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, name FROM topics ORDER BY id ASC")
            c10_topics = cursor.fetchall()
            topic_dict = {t[1]: t[0] for t in c10_topics}
            conn.close()
            
            sel_topic_name = st.selectbox("Target Class 10 Chapter:", list(topic_dict.keys()), key="adm_top_sel")
            target_t_id = topic_dict[sel_topic_name]
            
            tab_ext, tab_man, tab_del = st.tabs([
                "⚡ File / URL Question Extractor",
                "➕ Manual Single Question Upload",
                "📖 Browse & Delete Questions"
            ])
            
            with tab_ext:
                st.markdown("### 📤 Question Corner Auto-Extract Engine (PDF / DOCX / URL)")
                st.info("Upload PDF/DOCX question papers or paste a Website URL link. The system extracts text, normalizes Bengali fonts, and categorizes questions into 1, 2, 3, and 5 marks folders automatically!")
                
                source_type = st.radio("Select Extraction Source:", ["PDF / DOCX File Upload", "Website Page Link (URL)"], horizontal=True, key="adm_src_rad")
                
                extracted_text = ""
                if source_type == "PDF / DOCX File Upload":
                    file_obj = st.file_uploader("Upload Question File (.pdf or .docx)", type=["pdf", "docx"], key="adm_upl_file")
                    if file_obj is not None:
                        ext = file_obj.name.split('.')[-1].lower()
                        if ext == "pdf":
                            extracted_text = extract_text_from_pdf_file(file_obj)
                        elif ext == "docx" and HAS_DOCX:
                            doc_file = docx.Document(file_obj)
                            raw_txt = "\n".join([para.text for para in doc_file.paragraphs if para.text.strip()])
                            extracted_text = normalize_bengali_text(raw_txt)
                else:
                    web_url = st.text_input("Paste Web Page URL Link:", key="adm_url_in")
                    if st.button("🌐 Fetch Content from Web URL", key="adm_url_btn"):
                        if web_url.strip():
                            try:
                                req = urllib.request.Request(web_url.strip(), headers={'User-Agent': 'Mozilla/5.0'})
                                with urllib.request.urlopen(req, timeout=10) as resp:
                                    html_text = resp.read().decode('utf-8', errors='ignore')
                                    raw_text = re.sub(r'<[^>]+>', ' ', html_text)
                                    extracted_text = normalize_bengali_text(raw_text)
                                    st.success("Fetched and normalized web page content successfully!")
                            except Exception as e:
                                st.error(f"Error fetching URL: {e}")

                if extracted_text:
                    st.markdown("#### 📝 Normalized Extracted Text Preview (Editable):")
                    edited_extracted_text = st.text_area("Review Extracted Bengali Text:", value=extracted_text, height=220, key="adm_edit_ext_txt")
                    
                    parsed_candidates = parse_and_categorize_questions(edited_extracted_text)
                    st.success(f"Extracted {len(parsed_candidates)} candidate questions!")
                    
                    m1_qs = [q for q in parsed_candidates if q["marks"] == 1]
                    m2_qs = [q for q in parsed_candidates if q["marks"] == 2]
                    m3_qs = [q for q in parsed_candidates if q["marks"] == 3]
                    m5_qs = [q for q in parsed_candidates if q["marks"] == 5]
                    
                    f1, f2, f3, f5 = st.tabs([
                        f"📁 1 Mark ({len(m1_qs)})",
                        f"📁 2 Marks ({len(m2_qs)})",
                        f"📁 3 Marks ({len(m3_qs)})",
                        f"📁 5 Marks ({len(m5_qs)})"
                    ])
                    
                    with f1:
                        if m1_qs: st.dataframe(pd.DataFrame(m1_qs), use_container_width=True)
                    with f2:
                        if m2_qs: st.dataframe(pd.DataFrame(m2_qs), use_container_width=True)
                    with f3:
                        if m3_qs: st.dataframe(pd.DataFrame(m3_qs), use_container_width=True)
                    with f5:
                        if m5_qs: st.dataframe(pd.DataFrame(m5_qs), use_container_width=True)

                    if st.button("🚀 Save All Categorized Questions to Database", key="adm_save_cat_btn", use_container_width=True):
                        conn = get_connection()
                        cursor = conn.cursor()
                        saved_count = 0
                        for q_item in parsed_candidates:
                            q_bn = q_item["question"]
                            q_en = translate_geo_term(q_bn, "English")
                            cursor.execute("""
                                INSERT INTO questions (
                                    topic_id, question_text, question_text_en,
                                    option_a, option_b, option_c, option_d,
                                    correct_option, explanation, difficulty, is_descriptive, marks,
                                    model_answer, marking_scheme
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Medium', ?, ?, ?, ?)
                            """, (
                                target_t_id, q_bn, q_en,
                                q_item["opt_a"], q_item["opt_b"], q_item["opt_c"], q_item["opt_d"],
                                q_item["correct"], q_item["explanation"],
                                q_item["is_descriptive"], q_item["marks"],
                                q_bn if q_item["is_descriptive"] else "",
                                f"{q_item['marks']} Marks Evaluation Scheme"
                            ))
                            saved_count += 1
                        conn.commit()
                        conn.close()
                        st.success(f"🎉 Successfully saved {saved_count} categorized questions into Chapter `{sel_topic_name}`!")
                        st.rerun()

            with tab_man:
                st.markdown("### ➕ Manual Question Upload with Anti-Duplicate Intelligence")
                q_text_bn = st.text_area("Question Text (Bengali / Avro):", key="adm_man_q_bn")
                q_marks = st.selectbox("Select Marks:", [1, 2, 3, 5], key="adm_man_q_marks")
                
                if q_text_bn.strip():
                    match, ratio = check_duplicate_question(q_text_bn, target_t_id)
                    if match:
                        st.warning(f"⚠️ Duplicate Question Warning! ({ratio*100:.1f}% match in DB):")
                        st.caption(f"Existing Q_ID #{match[0]}: {match[1]}")

                if q_marks == 1:
                    col1, col2 = st.columns(2)
                    oa_bn = col1.text_input("Option A (Bengali/Avro):", key="adm_oa")
                    ob_bn = col2.text_input("Option B (Bengali/Avro):", key="adm_ob")
                    oc_bn = col1.text_input("Option C (Bengali/Avro):", key="adm_oc")
                    od_bn = col2.text_input("Option D (Bengali/Avro):", key="adm_od")
                    corr_opt = st.selectbox("Correct Option:", ["A", "B", "C", "D"], key="adm_co")
                    expl_bn = st.text_area("Explanation:", key="adm_ex")
                    
                    if st.button("Save 1 Mark MCQ to DB", key="adm_save_mcq", use_container_width=True):
                        if q_text_bn and oa_bn:
                            conn = get_connection()
                            cursor = conn.cursor()
                            q_en = translate_geo_term(q_text_bn, "English")
                            cursor.execute("""
                                INSERT INTO questions (
                                    topic_id, question_text, question_text_en,
                                    option_a, option_b, option_c, option_d,
                                    correct_option, explanation, difficulty, is_descriptive, marks
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Medium', 0, 1)
                            """, (target_t_id, q_text_bn, q_en, oa_bn, ob_bn, oc_bn, od_bn, corr_opt, expl_bn))
                            conn.commit()
                            conn.close()
                            st.success("🎉 Added 1 mark question!")
                            st.rerun()
                else:
                    m_ans_bn = st.text_area(f"Model Answer for {q_marks} Marks:", key="adm_m_ans")
                    m_sch_bn = st.text_area("Marking Scheme:", key="adm_m_sch")
                    if st.button(f"Save {q_marks} Marks Broad Question to DB", key="adm_save_broad", use_container_width=True):
                        if q_text_bn:
                            conn = get_connection()
                            cursor = conn.cursor()
                            q_en = translate_geo_term(q_text_bn, "English")
                            cursor.execute("""
                                INSERT INTO questions (
                                    topic_id, question_text, question_text_en,
                                    difficulty, is_descriptive, marks, model_answer, marking_scheme
                                ) VALUES (?, ?, ?, 'Hard', 1, ?, ?, ?)
                            """, (target_t_id, q_text_bn, q_en, q_marks, m_ans_bn, m_sch_bn))
                            conn.commit()
                            conn.close()
                            st.success(f"🎉 Added {q_marks} marks question!")
                            st.rerun()

            with tab_del:
                st.markdown("### 📖 Browse & Direct Question Delete Engine")
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id, question_text, marks, is_descriptive FROM questions WHERE topic_id = ? ORDER BY id DESC", (target_t_id,))
                q_rows = cursor.fetchall()
                conn.close()
                
                if not q_rows:
                    st.info("No questions stored in this chapter yet.")
                else:
                    for q_id, q_txt, q_m, is_d in q_rows:
                        col_q1, col_q2 = st.columns([5, 1])
                        col_q1.markdown(f"**Q_ID #{q_id} [{q_m} Marks]:** {q_txt}")
                        if col_q2.button(f"🗑️ Delete #{q_id}", key=f"adm_del_q_{q_id}"):
                            conn = get_connection()
                            cursor = conn.cursor()
                            cursor.execute("DELETE FROM questions WHERE id = ?", (q_id,))
                            conn.commit()
                            conn.close()
                            st.success(f"Deleted Question #{q_id}!")
                            st.rerun()

        elif st_nav == "📄 Upload Sequential Mock Tests & Suggestions":
            st.subheader("📄 Upload Sequential Mock Tests & Suggestions (PDF / DOCX)")
            
            t_type = st.radio("Select Test Type:", ["Chapter Wise Mock Test", "Final Mock Test", "Board Suggestions"], horizontal=True, key="adm_mock_type")
            
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM mock_tests WHERE test_type = ?", (t_type,))
            existing_cnt = cursor.fetchone()[0]
            conn.close()
            
            prefix = "chapter mock" if t_type == "Chapter Wise Mock Test" else ("final mock test" if t_type == "Final Mock Test" else "suggestion")
            auto_code = f"{prefix} - {existing_cnt + 1:03d}"
            
            st.info(f"Generated File Code: `{auto_code}`")
            up_file = st.file_uploader("Choose File (.pdf or .docx)", type=["pdf", "docx"], key="adm_mock_up_file")
            
            if st.button("🚀 Publish Mock Test / Suggestion Paper", key="adm_pub_mock_btn", use_container_width=True):
                if up_file is not None:
                    f_bytes = up_file.getvalue()
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO mock_tests (test_type, code_num, file_name, file_data, uploader)
                        VALUES (?, ?, ?, ?, ?)
                    """, (t_type, auto_code, up_file.name, f_bytes, st.session_state.full_name))
                    conn.commit()
                    conn.close()
                    st.success(f"🎉 Published `{auto_code}` successfully!")
                    st.rerun()

        elif st_nav == "📊 Analytics & Track Records":
            st.subheader("📊 Geo Lab Analytics & Student Track Records")
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT student_name, student_phone, school_name, district, exam_name, topic_name, score, total_questions, percentage, timestamp
                FROM student_scores ORDER BY timestamp DESC
            """)
            scores = cursor.fetchall()
            conn.close()
            
            if not scores:
                st.info("No student test records recorded yet.")
            else:
                df_scores = pd.DataFrame(scores, columns=["Student Name", "Phone", "School", "District", "Standard", "Topic", "Score", "Total Qs", "Percentage (%)", "Timestamp"])
                st.dataframe(df_scores, use_container_width=True)

# Permanent Developer Attribution Footer Block
st.markdown("""
    <div class="footer-block">
        <h3 style="margin-bottom: 5px; color: #38bdf8;">Prepared by - Shawon Kar, Sukannya Chakraborty</h3>
        <p style="margin: 3px 0; font-size: 1.1em; font-weight: 500;">M.Sc. in Geography (University Of Calcutta)</p>
        <p style="margin: 3px 0; font-size: 1.0em; color: #94a3b8;">B.Ed. (Baba Saheb Ambedkar Education University)</p>
        <p style="margin: 10px 0 0 0; font-weight: bold; color: #38bdf8; font-size: 1.2em;">📞 Ph No - 7001257277</p>
    </div>
""", unsafe_allow_html=True)
