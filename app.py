import streamlit as st
import os
import io
import re
import json
import urllib.request
import urllib.parse
import unicodedata
import ssl
import pandas as pd
from datetime import datetime, timedelta
from contextlib import contextmanager

import pg8000

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

st.set_page_config(
    page_title="WBBSE Geography Portal",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================================
# DATABASE — PostgreSQL via pg8000 (pure Python, no C deps)
# ============================================================================
def _get_db_url():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        try:
            url = st.secrets.get("DATABASE_URL", "")
        except Exception:
            url = ""
    return url

@st.cache_resource(show_spinner=False)
def get_connection_config():
    db_url = _get_db_url()
    if not db_url:
        return None
    m = re.match(r'postgres(?:ql)?://([^:]+):([^@]+)@([^:/]+):(\d+)/(.+)', db_url)
    if not m:
        return None
    return {
        "user": m.group(1),
        "password": urllib.parse.unquote(m.group(2)),
        "host": m.group(3),
        "port": int(m.group(4)),
        "database": m.group(5).split("?")[0],
    }

@contextmanager
def db_cursor():
    config = get_connection_config()
    if config is None:
        raise Exception("Database not configured")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    conn = pg8000.connect(**config, ssl_context=ctx, timeout=15)
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass

def _is_integrity_error(e):
    s = str(e).lower()
    return "unique" in s or "duplicate" in s or "primary key" in s

# ============================================================================
# BENGALI NORMALIZATION
# ============================================================================
def normalize_bengali_text(text):
    if not text:
        return ""
    text = unicodedata.normalize('NFC', text)
    text = re.sub(r'\u09C7([\u0985-\u09B9](\u09CD[\u0985-\u09B9])?)', lambda m: m.group(1) + '\u09C7', text)
    text = re.sub(r'\u09C8([\u0985-\u09B9](\u09CD[\u0985-\u09B9])?)', lambda m: m.group(1) + '\u09C8', text)
    text = re.sub(r'[\u200B\u200C\u200D]', '', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()

# ============================================================================
# PDF EXTRACTION
# ============================================================================
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
# DB MIGRATION
# ============================================================================
def verify_and_migrate_db():
    with db_cursor() as cur:
        cur.execute("""CREATE TABLE IF NOT EXISTS exams (
            id SERIAL PRIMARY KEY, name TEXT UNIQUE, description TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS topics (
            id SERIAL PRIMARY KEY, exam_id INTEGER, name TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS questions (
            id SERIAL PRIMARY KEY, topic_id INTEGER,
            pyq_year TEXT DEFAULT '', is_pyq INTEGER DEFAULT 0,
            question_text TEXT, question_text_en TEXT,
            option_a TEXT, option_a_en TEXT, option_b TEXT, option_b_en TEXT,
            option_c TEXT, option_c_en TEXT, option_d TEXT, option_d_en TEXT,
            correct_option CHAR(1), explanation TEXT, explanation_en TEXT,
            difficulty TEXT DEFAULT 'Medium', is_descriptive INTEGER DEFAULT 0,
            marks INTEGER DEFAULT 1, model_answer TEXT, model_answer_en TEXT,
            marking_scheme TEXT, marking_scheme_en TEXT,
            q_type TEXT DEFAULT 'MCQ')""")
        cur.execute("""CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY, username TEXT UNIQUE, password TEXT,
            role TEXT DEFAULT 'student', full_name TEXT, school_name TEXT,
            class_grade TEXT, phone TEXT, district TEXT,
            approved INTEGER DEFAULT 0, is_admin INTEGER DEFAULT 0,
            referral_code TEXT DEFAULT '', referral_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS student_scores (
            id SERIAL PRIMARY KEY, student_name TEXT, student_phone TEXT,
            school_name TEXT, district TEXT, exam_name TEXT, topic_name TEXT,
            score INTEGER, total_questions INTEGER, percentage REAL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS student_doubts (
            id SERIAL PRIMARY KEY, student_username TEXT, student_name TEXT,
            question_id INTEGER, assigned_teacher_username TEXT DEFAULT '',
            teacher_answer TEXT DEFAULT '', status TEXT DEFAULT 'Pending',
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS mock_tests (
            id SERIAL PRIMARY KEY, test_type TEXT, code_num TEXT,
            file_name TEXT, file_data BYTEA, uploader TEXT,
            price INTEGER DEFAULT 0, is_published INTEGER DEFAULT 1,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY, value TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS duplicate_log (
            id SERIAL PRIMARY KEY, original_q_id INTEGER, duplicate_q_id INTEGER,
            similarity REAL, removed_by TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS ask_corner (
            id SERIAL PRIMARY KEY, submitter_username TEXT, submitter_name TEXT,
            submitter_role TEXT, category TEXT, message TEXT,
            admin_reply TEXT DEFAULT '', status TEXT DEFAULT 'New',
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY, username TEXT, user_name TEXT,
            user_role TEXT, phone TEXT, item_type TEXT, item_id TEXT,
            amount INTEGER, upi_ref TEXT,
            status TEXT DEFAULT 'Pending Verification',
            admin_note TEXT DEFAULT '',
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approved_at TIMESTAMP)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS user_purchases (
            id SERIAL PRIMARY KEY, username TEXT, item_type TEXT, item_id TEXT,
            payment_id INTEGER, status TEXT DEFAULT 'Active',
            activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS exam_submissions (
            id SERIAL PRIMARY KEY, student_username TEXT, student_name TEXT,
            exam_type TEXT, exam_code TEXT, answer_file_name TEXT,
            answer_file_data BYTEA,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            checker_username TEXT DEFAULT '', status TEXT DEFAULT 'Submitted',
            corrected_file_name TEXT DEFAULT '', corrected_file_data BYTEA,
            corrected_at TIMESTAMP, admin_note TEXT DEFAULT '',
            teacher_corrected_file_name TEXT DEFAULT '',
            teacher_corrected_file_data BYTEA,
            teacher_note TEXT DEFAULT '', teacher_submitted_at TIMESTAMP)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS teacher_submissions (
            id SERIAL PRIMARY KEY, teacher_username TEXT, teacher_name TEXT,
            sub_type TEXT, title TEXT, description TEXT,
            file_name TEXT, file_data BYTEA,
            status TEXT DEFAULT 'Pending Admin Review',
            admin_note TEXT DEFAULT '', published_mock_id INTEGER DEFAULT 0,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

        cur.execute("""INSERT INTO system_settings (key, value) VALUES ('portal_url', 'https://geography-exam-portal.onrender.com') ON CONFLICT (key) DO NOTHING""")
        cur.execute("""INSERT INTO system_settings (key, value) VALUES ('upi_id', 'shawonkar6466-1@oksbi') ON CONFLICT (key) DO NOTHING""")
        cur.execute("""INSERT INTO system_settings (key, value) VALUES ('full_access_price', '100') ON CONFLICT (key) DO NOTHING""")
        cur.execute("""INSERT INTO exams (id, name, description) VALUES (1, 'Madhyamik Class 10', 'WBBSE Class 10 Geography') ON CONFLICT (id) DO NOTHING""")

        cur.execute("SELECT COUNT(*) FROM topics")
        if cur.fetchone()[0] == 0:
            default_topics = [
                "১. বহির্জাত প্রক্রিয়া ও তাদের দ্বারা সৃষ্ট ভূমিরূপ / Exogenic Processes and Created Landforms",
                "২. বায়ুমণ্ডল / Atmosphere",
                "৩. বারিমণ্ডল / Hydrosphere",
                "৪. বর্জ্য ব্যবস্থাপনা / Waste Management",
                "৫. ভারত / India",
                "৬. উপগ্রহ চিত্র ও ভূ-বৈচিত্র্যসূচক মানচিত্র / Satellite Imagery and Topographical Maps"
            ]
            for t_name in default_topics:
                cur.execute("INSERT INTO topics (exam_id, name) VALUES (1, %s)", (t_name,))

try:
    if _get_db_url():
        verify_and_migrate_db()
except Exception as e:
    print(f"Migration error: {e}")

ADMIN_PASSCODE = "admin123"

# ============================================================================
# LANGUAGE
# ============================================================================
def T(bn, en):
    lang = st.session_state.get('language', 'Bengali')
    return bn if lang == "Bengali" else en

BN_EN_TERMS = {
    "কোনটি": "Which one", "কোন": "Which", "কে": "Who", "কি": "What", "কী": "What",
    "কেন": "Why", "কোথায়": "Where", "কখন": "When", "কিভাবে": "How", "কত": "How many",
    "সর্বপ্রথম": "First", "সর্বপ্রধান": "Most important", "প্রধান": "Main", "মূল": "Main",
    "নাম": "Name", "উদাহরণ": "Example", "বিশেষ": "Special", "ভিন্ন": "Different",
    "ভূগোল": "Geography", "ভূবিজ্ঞান": "Geology", "ভূমিরূপ": "Landform",
    "ভূমিকম্প": "Earthquake", "বহির্জাত": "Exogenic", "অন্তর্জাত": "Endogenic",
    "প্রক্রিয়া": "Process", "পর্যায়ন": "Gradation", "অবক্ষয়": "Weathering",
    "ক্ষয়": "Erosion", "নদী": "River", "বদ্বীপ": "Delta", "জলপ্রপাত": "Waterfall",
    "হিমবাহ": "Glacier", "বায়ু": "Wind", "সমুদ্র": "Sea", "মহাসাগর": "Ocean",
    "পাহাড়": "Mountain", "পর্বত": "Mountain", "মালভূমি": "Plateau",
    "সমভূমি": "Plain", "উপত্যকা": "Valley", "গিরিখাত": "Canyon",
    "বায়ুমণ্ডল": "Atmosphere", "বারিমণ্ডল": "Hydrosphere", "জীবমণ্ডল": "Biosphere",
    "জলবায়ু": "Climate", "আবহাওয়া": "Weather", "তাপমাত্রা": "Temperature",
    "বৃষ্টিপাত": "Rainfall", "মৌসুমি": "Monsoon", "বর্ষা": "Monsoon",
    "বর্জ্য": "Waste", "ব্যবস্থাপনা": "Management", "দূষণ": "Pollution",
    "পরিবেশ": "Environment", "ভারত": "India", "বাংলাদেশ": "Bangladesh",
    "পশ্চিমবঙ্গ": "West Bengal", "কলকাতা": "Kolkata", "দিল্লি": "Delhi",
    "হিমালয়": "Himalaya", "গঙ্গা": "Ganga", "ব্রহ্মপুত্র": "Brahmaputra",
    "উপগ্রহ": "Satellite", "চিত্র": "Image", "মানচিত্র": "Map",
    "ভূ-বৈচিত্র্যসূচক": "Topographical", "স্কেল": "Scale", "দিক": "Direction",
    "প্রথম": "First", "সঠিক": "Correct", "ভুল": "Wrong", "প্রাকৃতিক": "Natural",
    "নিচের কোনটি": "Which of the following", "ব্যাখ্যা করুন": "Explain",
    "প্রভাব": "Effect", "ব্যবহার": "Usage",
}

def translate_geo_simple(bn_text):
    if not bn_text or not isinstance(bn_text, str):
        return bn_text or ""
    bn_count = sum(1 for c in bn_text if '\u0980' <= c <= '\u09FF')
    if bn_count < 2:
        return bn_text
    result = bn_text
    for bn in sorted(BN_EN_TERMS.keys(), key=len, reverse=True):
        if bn in result:
            result = result.replace(bn, " " + BN_EN_TERMS[bn] + " ")
    return re.sub(r'\s+', ' ', result).strip()

def get_q_text(bn_text, en_text):
    lang = st.session_state.get('language', 'Bengali')
    if lang == "Bengali":
        return bn_text or en_text or ""
    if en_text and en_text.strip():
        return en_text
    if bn_text:
        return translate_geo_simple(bn_text)
    return ""

# ============================================================================
# CACHED
# ============================================================================
@st.cache_data(ttl=60, show_spinner=False)
def cached_topics():
    try:
        with db_cursor() as cur:
            cur.execute("SELECT id, name FROM topics ORDER BY id ASC")
            return cur.fetchall()
    except Exception:
        return []

@st.cache_data(ttl=15, show_spinner=False)
def cached_has_purchase(username, item_type, item_id):
    try:
        with db_cursor() as cur:
            cur.execute("""SELECT COUNT(*) FROM user_purchases
                WHERE username = %s AND item_type = %s AND item_id = %s AND status = 'Active'""",
                (username, item_type, str(item_id)))
            return cur.fetchone()[0] > 0
    except Exception:
        return False

@st.cache_data(ttl=30, show_spinner=False)
def cached_questions_for_topic(topic_id):
    try:
        with db_cursor() as cur:
            cur.execute("""SELECT id, question_text, question_text_en, option_a, option_a_en, option_b, option_b_en,
                option_c, option_c_en, option_d, option_d_en, correct_option, explanation, explanation_en,
                difficulty, is_descriptive, marks, model_answer, model_answer_en, marking_scheme, marking_scheme_en, q_type
                FROM questions WHERE topic_id = %s""", (topic_id,))
            return cur.fetchall()
    except Exception:
        return []

# ============================================================================
# SMART MCQ PARSER
# ============================================================================
def smart_parse_mcq_text(text):
    text = normalize_bengali_text(text)
    lines = text.split('\n')
    OPT_PAT = re.compile(r'^\s*[\(\[]?\s*([কখগঘABCD])\s*[\)\]]\s*[\.\)]?\s*(.*)$', re.UNICODE)
    ANS_PAT = re.compile(r'(?:✅|✔|☑)?\s*(?:সঠিক\s*উত্তর|সঠিক\s*উঃ|Correct\s*Answer|Answer|উত্তর)\s*[:\-–]?\s*[\(\[]?\s*([কখগঘABCD])', re.IGNORECASE | re.UNICODE)
    NOTE_PAT = re.compile(r'^\s*(?:নোট|ব্যাখ্যা|Explanation|Note)\s*[:\-–]\s*(.*)$', re.IGNORECASE | re.UNICODE)
    QNUM_PAT = re.compile(r'^\s*(?:Q\s*\d+[\.\):]|প্রঃ?\s*\d+[\.\):]|\d+[\.\)])\s*(.*)$', re.IGNORECASE | re.UNICODE)
    B2A = {'ক': 'A', 'খ': 'B', 'গ': 'C', 'ঘ': 'D'}
    questions = []
    cur = {'question': '', 'options': {'A': '', 'B': '', 'C': '', 'D': ''}, 'correct': 'A', 'explanation': ''}
    for raw_line in lines:
        s = raw_line.strip()
        if not s:
            continue
        ma = ANS_PAT.search(s)
        if ma:
            letter = B2A.get(ma.group(1), 'A')
            cur['correct'] = letter
            tail = s[ma.end():].strip()
            tail = re.sub(r'^[\)\]\.\,\:\-\s]+', '', tail)
            if tail and not cur['options'].get(letter):
                cur['options'][letter] = tail
            continue
        mn = NOTE_PAT.match(s)
        if mn:
            cur['explanation'] = mn.group(1).strip()
            continue
        mo = OPT_PAT.match(s)
        if mo:
            letter = B2A.get(mo.group(1))
            if letter and not cur['options'].get(letter):
                cur['options'][letter] = mo.group(2).strip()
                continue
        mq = QNUM_PAT.match(s)
        if mq and cur['question'] and any(cur['options'].values()):
            questions.append(cur)
            cur = {'question': mq.group(1).strip(), 'options': {'A': '', 'B': '', 'C': '', 'D': ''}, 'correct': 'A', 'explanation': ''}
            continue
        if not any(cur['options'].values()):
            cur['question'] = (cur['question'] + ' ' + s).strip() if cur['question'] else s
        else:
            cur['explanation'] = (cur['explanation'] + ' ' + s).strip() if cur['explanation'] else s
    if cur['question'] and any(cur['options'].values()):
        questions.append(cur)
    return questions

def detect_mcq_format(text):
    cnt = 0
    for line in text.split('\n'):
        if re.match(r'^[\(\[]?\s*[কখগঘ]\s*[\)\]]', line.strip(), re.UNICODE):
            cnt += 1
    return cnt >= 3

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
            if re.search(r'([২2]\s*নম্বর|2\s*marks?)', line, re.IGNORECASE):
                m_val = 2
            elif re.search(r'([৩3]\s*নম্বর|3\s*marks?)', line, re.IGNORECASE):
                m_val = 3
            elif re.search(r'([৫5]\s*নম্বর|5\s*marks?)', line, re.IGNORECASE):
                m_val = 5
            current_q = {
                "question": normalize_bengali_text(q_txt), "marks": m_val,
                "opt_a": "", "opt_b": "", "opt_c": "", "opt_d": "",
                "correct": "A", "explanation": "",
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
    try:
        with db_cursor() as cur:
            cur.execute("SELECT id, question_text FROM questions WHERE topic_id = %s", (topic_id,))
            existing_qs = cur.fetchall()
    except Exception:
        return None, 0.0
    candidate_norm = re.sub(r'[^\w\s]', '', normalize_bengali_text(new_q_text)).lower()
    best_match = None
    highest_ratio = 0.0
    for q_id, q_text in existing_qs:
        q_norm = re.sub(r'[^\w\s]', '', normalize_bengali_text(q_text)).lower()
        ratio = difflib.SequenceMatcher(None, candidate_norm, q_norm).ratio()
        if ratio > highest_ratio:
            highest_ratio = ratio
            best_match = (q_id, q_text)
    if highest_ratio >= threshold:
        return best_match, highest_ratio
    return None, highest_ratio

def user_has_purchase(username, item_type, item_id):
    return cached_has_purchase(username, item_type, item_id)

def has_full_access(username):
    return user_has_purchase(username, "FULL_ACCESS", "ALL")

def get_setting(key, default=""):
    try:
        with db_cursor() as cur:
            cur.execute("SELECT value FROM system_settings WHERE key = %s", (key,))
            row = cur.fetchone()
        return row[0] if row else default
    except Exception:
        return default

def get_portal_url():
    return get_setting("portal_url", "https://geography-exam-portal.onrender.com")

def get_upi_id():
    return get_setting("upi_id", "shawonkar6466-1@oksbi")

def get_full_access_price():
    try:
        return int(get_setting("full_access_price", "100"))
    except Exception:
        return 100

# ============================================================================
# SESSION STATE
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

try:
    query_ref = st.query_params.get("ref", "")
    if query_ref:
        st.session_state.referred_by = query_ref
except Exception:
    pass

# ============================================================================
# CSS
# ============================================================================
st.markdown("""
    <style>
    .stApp, [data-testid="stAppViewContainer"], .main, .block-container {
        background-color: #f1f5f9 !important; color: #0f172a !important;
    }
    section[data-testid="stSidebar"] { background-color: #ffffff !important; min-width: 280px !important; }
    section[data-testid="stSidebar"] * { color: #0f172a !important; }
    h1, h2, h3, h4, h5, h6, p, span, label, div, small, strong, em,
    .stMarkdown, .stMarkdown * { color: #0f172a !important; }
    .stTextInput input, .stTextArea textarea, .stSelectbox select,
    .stNumberInput input, input, textarea, select {
        background-color: #ffffff !important; color: #0f172a !important;
        border: 1.5px solid #475569 !important; border-radius: 8px !important;
        font-weight: 600 !important;
    }
    [data-baseweb="popover"], [data-baseweb="menu"], [role="listbox"], [role="option"] {
        background-color: #ffffff !important; color: #0f172a !important;
    }
    .stRadio label, .stRadio div { color: #0f172a !important; }
    [data-testid="stExpander"] summary { background-color: #f8fafc !important; color: #0f172a !important; font-weight: 600 !important; }
    [data-testid="stExpander"] { background-color: #ffffff !important; border: 1.5px solid #cbd5e1 !important; border-radius: 10px !important; }
    .stTabs [data-baseweb="tab-list"] { background-color: #e2e8f0 !important; border-radius: 10px; padding: 6px; }
    .stTabs [data-baseweb="tab"] { background-color: transparent !important; color: #475569 !important; font-weight: 600 !important; }
    .stTabs [aria-selected="true"] { background-color: #ffffff !important; color: #1d4ed8 !important; }
    .stButton > button, .stDownloadButton > button {
        background-color: #2563eb !important; color: #ffffff !important;
        border: none !important; border-radius: 8px !important;
        font-weight: 700 !important; padding: 10px 18px !important;
    }
    .stButton > button:hover { background-color: #1d4ed8 !important; }
    .stButton > button p, .stDownloadButton > button p { color: #ffffff !important; }
    [data-testid="stForm"] { background-color: #ffffff !important; border: 1.5px solid #cbd5e1 !important; border-radius: 12px !important; padding: 20px !important; }
    [data-testid="stMetric"] { background-color: #ffffff !important; padding: 16px !important; border-radius: 12px !important; border: 1.5px solid #cbd5e1 !important; }
    [data-testid="stMetricValue"], [data-testid="stMetricLabel"] { color: #0f172a !important; }
    .stDataFrame, .stDataFrame * { color: #0f172a !important; }
    .stAlert, .stAlert * { color: #0f172a !important; }
    .header-box {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 50%, #0284c7 100%);
        padding: 28px; border-radius: 16px; color: #ffffff !important;
        text-align: center; margin-bottom: 25px; box-shadow: 0 10px 25px rgba(0,0,0,0.15);
    }
    .header-box h1 { color: #ffffff !important; font-size: 2rem !important; font-weight: 700 !important; margin: 0; }
    .header-box p { color: #e0e7ff !important; margin-top: 8px; }
    .card-short {
        background-color: #ffffff !important; color: #000000 !important;
        padding: 22px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        border-left: 6px solid #2563eb; margin-bottom: 18px;
    }
    .card-short h4 { color: #000000 !important; font-weight: 900 !important; }
    .card-broad {
        background-color: #ffffff !important; color: #000000 !important;
        padding: 22px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        border-left: 6px solid #7c3aed; margin-bottom: 18px;
    }
    .card-broad h4 { color: #000000 !important; font-weight: 900 !important; }
    .price-card { background: linear-gradient(135deg, #ffffff 0%, #eff6ff 100%);
        padding: 22px; border-radius: 14px; text-align: center;
        border: 2px solid #2563eb; margin-bottom: 15px; }
    .price-card h3 { color: #1e3a8a !important; margin: 0 0 8px 0; font-size: 1.3rem !important; }
    .price-card p { color: #475569 !important; }
    .price-tag { font-size: 2.2rem; font-weight: 900; color: #059669 !important; margin: 10px 0; }
    .price-card-premium { background: linear-gradient(135deg, #fef3c7 0%, #fde68a 50%, #fcd34d 100%);
        padding: 26px; border-radius: 14px; text-align: center;
        border: 3px solid #f59e0b; margin-bottom: 15px; }
    .price-card-premium h3 { color: #78350f !important; margin: 0 0 8px 0; }
    .price-card-premium p { color: #92400e !important; }
    .price-tag-premium { font-size: 2.6rem; font-weight: 900; color: #b45309 !important; margin: 12px 0; }
    .footer-block { background-color: #0f172a; color: #f8fafc; padding: 28px;
        border-radius: 14px; text-align: center; margin-top: 50px; border-top: 5px solid #2563eb; }
    .footer-block * { color: #f8fafc !important; }
    .footer-block h3 { color: #38bdf8 !important; }
    .lock-box { background: #fef3c7; border: 2px dashed #f59e0b; padding: 20px; border-radius: 12px; text-align: center; margin-bottom: 15px; }
    .lock-box * { color: #78350f !important; }
    .ask-corner-card { background: #ffffff; padding: 15px; border-radius: 10px; border-left: 5px solid #16a34a; margin-bottom: 12px; }
    .ask-corner-card * { color: #0f172a !important; }
    .assigned-card { background: linear-gradient(135deg, #fef3c7 0%, #fef9c3 100%); padding: 18px; border-radius: 12px; border-left: 5px solid #f59e0b; margin-bottom: 14px; }
    .assigned-card * { color: #78350f !important; }
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    </style>
""", unsafe_allow_html=True)

# ============================================================================
# SIDEBAR
# ============================================================================
st.sidebar.markdown("<h1 style='text-align:center;'>🌍</h1>", unsafe_allow_html=True)
st.sidebar.title("🌍 WBBSE Geo Lab Portal")
st.session_state.language = st.sidebar.radio(T("🌐 Language / ভাষা", "🌐 Language"), ["Bengali", "English"], key="lang_radio")
lang = st.session_state.language

if lang == "Bengali":
    st.markdown("""
        <div class="header-box">
            <h1>🌍 পশ্চিমবঙ্গ ভূগোল পরীক্ষা প্রস্তুতি ও ডিজিটাল ল্যাব</h1>
            <p>ওয়েস্ট বেঙ্গল বোর্ড (WBBSE) দশম শ্রেণী অফিসিয়াল ভূগোল সিলেবাস প্র্যাকটিস হাব</p>
        </div>""", unsafe_allow_html=True)
else:
    st.markdown("""
        <div class="header-box">
            <h1>🌍 West Bengal Board Geography Portal</h1>
            <p>WBBSE Class 10 Geography — Practice Hub</p>
        </div>""", unsafe_allow_html=True)

if not _get_db_url():
    st.error("⚠️ **DATABASE_URL not configured!**")
    st.info("Render → Your Service → Environment → Add `DATABASE_URL`")
    st.stop()

# ============================================================================
# LOGIN / REGISTRATION
# ============================================================================
if not st.session_state.logged_in:
    tab_login, tab_student_reg, tab_teacher_reg = st.tabs([
        T("🔑 Login", "🔑 Login"),
        T("🎓 Student Register", "🎓 Student Register"),
        T("👨‍🏫 Teacher Register", "👨‍🏫 Teacher Register")
    ])
    
    with tab_login:
        st.subheader(T("Sign in", "Sign in"))
        role_select = st.radio(T("Role:", "Role:"), ["Student", "Teacher", "Admin"], horizontal=True, key="login_role")
        login_user = st.text_input(T("Phone / Username", "Phone / Username"), key="login_u")
        login_pass = st.text_input(T("Password", "Password"), type="password", key="login_p")
        if st.button(T("Enter Portal", "Enter Portal"), use_container_width=True, key="login_submit_btn"):
            if role_select == "Admin" and login_user == "admin" and login_pass == ADMIN_PASSCODE:
                st.session_state.logged_in = True
                st.session_state.username = "admin"
                st.session_state.role = "admin"
                st.session_state.full_name = "Shawon Kar (Head Admin)"
                st.rerun()
            else:
                try:
                    with db_cursor() as cur:
                        cur.execute("""SELECT password, role, full_name, school_name, phone, district, approved 
                            FROM users WHERE (username = %s OR phone = %s)""", (login_user, login_user))
                        row = cur.fetchone()
                    if row:
                        db_pass, db_role, f_name, sch, ph, dist, approved = row
                        if db_pass == login_pass:
                            if approved == 1:
                                st.session_state.logged_in = True
                                st.session_state.username = login_user
                                st.session_state.role = db_role
                                st.session_state.full_name = f_name
                                st.session_state.school_name = sch or ""
                                st.session_state.phone = ph or ""
                                st.session_state.district = dist or ""
                                st.rerun()
                            else:
                                st.warning(T("⚠️ Admin approval pending.", "⚠️ Admin approval pending."))
                        else:
                            st.error(T("❌ Wrong Password.", "❌ Wrong Password."))
                    else:
                        st.error(T("❌ Account not found.", "❌ Account not found."))
                except Exception as e:
                    st.error(f"DB Error: {e}")
    
    with tab_student_reg:
        st.subheader(T("New Student Registration", "New Student Registration"))
        s_name = st.text_input(T("Name", "Name"), key="s_name")
        s_school = st.text_input(T("School", "School"), key="s_sch")
        s_class = st.selectbox(T("Class", "Class"), ["Class 10 (Madhyamik)"], key="s_cls")
        s_phone = st.text_input(T("Phone", "Phone"), key="s_ph")
        s_dist = st.text_input(T("District", "District"), key="s_dist")
        s_pass = st.text_input(T("Password", "Password"), type="password", key="s_pass")
        ref_default_s = st.session_state.get('referred_by', '')
        if ref_default_s:
            st.success(f"🎁 Referral detected: `{ref_default_s}`")
        s_ref = st.text_input(T("Referral Code (Optional)", "Referral Code (Optional)"), value=ref_default_s, key="s_ref")
        if st.button(T("Submit Student Registration", "Submit Student Registration"), use_container_width=True, key="student_reg_submit_btn"):
            if s_name and s_school and s_phone and s_pass:
                try:
                    with db_cursor() as cur:
                        auto_ref = f"GEO-REF-{s_phone[-4:] if len(s_phone) >= 4 else '10'}"
                        cur.execute("""INSERT INTO users 
                            (username, password, role, full_name, school_name, class_grade, phone, district, approved, is_admin, referral_code)
                            VALUES (%s, %s, 'student', %s, %s, %s, %s, %s, 0, 0, %s)""",
                            (s_phone, s_pass, s_name, s_school, s_class, s_phone, s_dist, auto_ref))
                        if s_ref.strip():
                            cur.execute("UPDATE users SET referral_count = referral_count + 1 WHERE referral_code = %s", (s_ref.strip(),))
                    st.success(T("🎉 Registration requested!", "🎉 Registration requested!"))
                except Exception as e:
                    if _is_integrity_error(e):
                        st.error(T("❌ Account exists.", "❌ Account already exists."))
                    else:
                        st.error(f"Error: {e}")
            else:
                st.error(T("⚠️ Fill all fields.", "⚠️ Fill all fields."))
    
    with tab_teacher_reg:
        st.subheader(T("New Teacher Registration", "New Teacher Registration"))
        t_name = st.text_input(T("Name", "Name"), key="t_name")
        t_school = st.text_input(T("School", "School"), key="t_sch")
        t_phone = st.text_input(T("Phone", "Phone"), key="t_ph")
        t_dist = st.text_input(T("District", "District"), key="t_dist")
        t_pass = st.text_input(T("Password", "Password"), type="password", key="t_pass")
        ref_default_t = st.session_state.get('referred_by', '')
        if ref_default_t:
            st.success(f"🎁 Referral detected: `{ref_default_t}`")
        t_ref = st.text_input(T("Referral Code (Optional)", "Referral Code (Optional)"), value=ref_default_t, key="t_ref")
        if st.button(T("Submit Teacher Registration", "Submit Teacher Registration"), use_container_width=True, key="teacher_reg_submit_btn"):
            if t_name and t_school and t_phone and t_pass:
                try:
                    with db_cursor() as cur:
                        auto_t_ref = f"GEO-REF-T{t_phone[-4:] if len(t_phone) >= 4 else '99'}"
                        cur.execute("""INSERT INTO users 
                            (username, password, role, full_name, school_name, class_grade, phone, district, approved, is_admin, referral_code)
                            VALUES (%s, %s, 'teacher', %s, %s, 'Faculty', %s, %s, 0, 0, %s)""",
                            (t_phone, t_pass, t_name, t_school, t_phone, t_dist, auto_t_ref))
                        if t_ref.strip():
                            cur.execute("UPDATE users SET referral_count = referral_count + 1 WHERE referral_code = %s", (t_ref.strip(),))
                    st.success(T("🎉 Registration requested!", "🎉 Registration requested!"))
                except Exception as e:
                    if _is_integrity_error(e):
                        st.error(T("❌ Account exists.", "❌ Account already exists."))
                    else:
                        st.error(f"Error: {e}")
            else:
                st.error(T("⚠️ Fill all fields.", "⚠️ Fill all fields."))

else:
    # ========================================================================
    # LOGGED-IN INTERFACE
    # ========================================================================
    st.sidebar.markdown(f"👤 **{T('নাম', 'Name')}:** `{st.session_state.full_name}`")
    st.sidebar.markdown(f"🎭 **{T('ভূমিকা', 'Role')}:** `{st.session_state.role.capitalize()}`")
    if st.session_state.school_name:
        st.sidebar.caption(f"🏫 {st.session_state.school_name} | {st.session_state.district}")
    
    if st.session_state.role == "admin":
        st.sidebar.markdown("---")
        st.sidebar.markdown("👑 **Admin Super-Control**")
        st.session_state.admin_view_mode = st.sidebar.radio(
            T("View Portal As:", "View Portal As:"),
            ["Admin Control Panel", "Teacher View", "Student View"],
            key="adm_view_mode"
        )
    
    if st.sidebar.button(T("Logout", "Logout"), key="logout_btn"):
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
    
    teacher_has_assignments = False
    if active_view_role == "teacher":
        try:
            with db_cursor() as cur:
                cur.execute("""SELECT COUNT(*) FROM exam_submissions 
                    WHERE checker_username = %s AND status = 'Under Check'""", (st.session_state.username,))
                teacher_has_assignments = cur.fetchone()[0] > 0
        except Exception:
            pass
    
    if active_view_role == "student":
        st_nav = st.sidebar.selectbox(T("🎯 Navigation", "🎯 Navigation"), [
            T("🏠 Dashboard", "🏠 Dashboard"),
            T("📖 Practice Center", "📖 Practice Center"),
            T("❓ My Help / Doubt Requests", "❓ My Help / Doubt Requests"),
            T("📄 Mock Tests & Suggestions", "📄 Mock Tests & Suggestions"),
            T("📝 My Exam Submissions", "📝 My Exam Submissions"),
            T("📁 Madhyamik Drive Papers", "📁 Madhyamik Drive Papers"),
            T("🎁 Share & Referral Links", "🎁 Share & Referral Links"),
            T("💡 Ask Corner (Suggestions)", "💡 Ask Corner (Suggestions)"),
            T("💳 Pricing & Payment", "💳 Pricing & Payment")
        ], key="nav_student")
    elif active_view_role == "teacher":
        teacher_menu = [
            T("📥 Assigned Student Doubts", "📥 Assigned Student Doubts"),
            T("📖 Question Bank Manager", "📖 Question Bank Manager"),
        ]
        if teacher_has_assignments:
            teacher_menu.append(T("📝 Check Assigned Answer Sheets", "📝 Check Assigned Answer Sheets"))
        teacher_menu += [
            T("📤 Send Suggestions to Admin", "📤 Send Suggestions to Admin"),
            T("👨‍🏫 Student Track Records", "👨‍🏫 Student Track Records"),
            T("📁 Madhyamik Drive Papers", "📁 Madhyamik Drive Papers"),
            T("🎁 Share & Referral Links", "🎁 Share & Referral Links"),
            T("💡 Ask Corner (Suggestions)", "💡 Ask Corner (Suggestions)"),
            T("💳 Pricing & Payment", "💳 Pricing & Payment")
        ]
        st_nav = st.sidebar.selectbox(T("🎯 Navigation", "🎯 Navigation"), teacher_menu, key="nav_teacher")
    else:
        st_nav = st.sidebar.selectbox(T("🎯 Navigation", "🎯 Navigation"), [
            T("🛡️ User Approvals", "🛡️ User Approvals"),
            T("❓ Student Doubt Assignment Hub", "❓ Student Doubt Assignment Hub"),
            T("📖 Question Bank Manager", "📖 Question Bank Manager"),
            T("📄 Upload Mock Tests & Suggestions", "📄 Upload Mock Tests & Suggestions"),
            T("📤 Teacher Submissions Review", "📤 Teacher Submissions Review"),
            T("💡 Ask Corner Suggestions", "💡 Ask Corner Suggestions"),
            T("💳 Payment Verifications", "💳 Payment Verifications"),
            T("📝 Exam Answer Sheet Checking", "📝 Exam Answer Sheet Checking"),
            T("📁 Madhyamik Drive Papers", "📁 Madhyamik Drive Papers"),
            T("📊 Analytics & Track Records", "📊 Analytics & Track Records"),
            T("🎁 Share & Referral Links", "🎁 Share & Referral Links")
        ], key="nav_admin")
    
    # ---------- Madhyamik Drive ----------
    if st_nav == T("📁 Madhyamik Drive Papers", "📁 Madhyamik Drive Papers"):
        st.subheader("📁 Official Madhyamik Google Drive Papers")
        st.markdown("""
            <div style="background-color: #eff6ff; border: 2px solid #2563eb; padding: 22px; border-radius: 12px; margin-bottom: 20px;">
                <h3 style="color: #1e3a8a; margin-top:0;">📥 Official Madhyamik Board Question Papers</h3>
                <p style="color: #0f172a;">২০১৭ থেকে ২০২৬ সালের সব অফিশিয়াল মাধ্যমিক ভূগোল প্রশ্নপত্র:</p>
                <a href="https://drive.google.com/drive/folders/1q4cLE5sYcjElqSnZPQ4Tx4lkbrB-U-pj?usp=drive_link" target="_blank" style="background-color: #2563eb; color: white; padding: 10px 20px; border-radius: 8px; text-decoration: none; font-weight: bold; display: inline-block;">🔗 Open Google Drive Folder</a>
            </div>""", unsafe_allow_html=True)
    
    # ---------- Share & Referral ----------
    elif st_nav == T("🎁 Share & Referral Links", "🎁 Share & Referral Links"):
        st.subheader(T("🎁 Refer Friends & Share Portal", "🎁 Refer Friends & Share Portal"))
        try:
            with db_cursor() as cur:
                cur.execute("SELECT referral_code, referral_count FROM users WHERE username = %s", (st.session_state.username,))
                ref_row = cur.fetchone()
        except Exception:
            ref_row = None
        current_portal_url = get_portal_url()
        my_code = ref_row[0] if ref_row and ref_row[0] else "GEO-REF-10"
        my_count = ref_row[1] if ref_row and ref_row[1] else 0
        
        if role == "admin":
            st.markdown("#### 🌐 Portal URL Configuration")
            new_url_val = st.text_input("Official Web Link:", value=current_portal_url, key="adm_portal_url")
            if st.button("💾 Save Portal URL", key="save_portal_url_btn"):
                try:
                    with db_cursor() as cur:
                        cur.execute("""INSERT INTO system_settings (key, value) VALUES ('portal_url', %s)
                            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""", (new_url_val.strip(),))
                    st.cache_data.clear()
                    st.success("✅ Updated!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
        
        col1, col2 = st.columns(2)
        col1.metric(T("Your Referral Code", "Your Referral Code"), my_code)
        col2.metric(T("Successful Referrals", "Successful Referrals"), f"{my_count} / 100")
        st.progress(min(my_count / 100.0, 1.0))
        if my_count >= 100:
            st.balloons()
        
        ref_link = f"{current_portal_url}?ref={my_code}"
        share_msg = f"🌍 Join WBBSE Class 10 Geography Portal!\n\n👉 Click: {ref_link}\n\n🔑 Code: {my_code}"
        encoded_msg = urllib.parse.quote(share_msg)
        
        col_wa, col_sms, col_fb = st.columns(3)
        col_wa.markdown(f'<a href="https://api.whatsapp.com/send?text={encoded_msg}" target="_blank" style="background-color:#22c55e; color:white; padding:10px 16px; border-radius:8px; text-decoration:none; font-weight:bold; display:block; text-align:center;">📱 WhatsApp</a>', unsafe_allow_html=True)
        col_sms.markdown(f'<a href="sms:?body={encoded_msg}" style="background-color:#0284c7; color:white; padding:10px 16px; border-radius:8px; text-decoration:none; font-weight:bold; display:block; text-align:center;">💬 SMS</a>', unsafe_allow_html=True)
        col_fb.markdown(f'<a href="https://www.facebook.com/sharer/sharer.php?u={urllib.parse.quote(ref_link)}&quote={encoded_msg}" target="_blank" style="background-color:#1d4ed8; color:white; padding:10px 16px; border-radius:8px; text-decoration:none; font-weight:bold; display:block; text-align:center;">📘 Facebook</a>', unsafe_allow_html=True)
    
    # ---------- Ask Corner ----------
    elif st_nav == T("💡 Ask Corner (Suggestions)", "💡 Ask Corner (Suggestions)"):
        st.subheader(T("💡 Ask Corner — Share Your Ideas!", "💡 Ask Corner — Share Your Ideas!"))
        with st.form("ask_corner_form"):
            ask_cat = st.selectbox(T("Category:", "Category:"), [
                "💡 Feature Idea", "🐛 Bug", "📚 Question Bank", "🎨 Design", "💰 Pricing", "🎯 Feedback", "❓ Other"
            ], key="ask_cat_sel")
            ask_msg = st.text_area(T("Message:", "Message:"), height=180, key="ask_msg_in")
            if st.form_submit_button(T("📤 Submit to Admin", "📤 Submit to Admin"), use_container_width=True):
                if ask_msg.strip():
                    try:
                        with db_cursor() as cur:
                            cur.execute("""INSERT INTO ask_corner (submitter_username, submitter_name, submitter_role, category, message)
                                VALUES (%s, %s, %s, %s, %s)""",
                                (st.session_state.username, st.session_state.full_name, st.session_state.role, ask_cat, ask_msg.strip()))
                        st.success(T("🎉 Sent!", "🎉 Sent!"))
                    except Exception as e:
                        st.error(f"Error: {e}")
        
        st.markdown("---")
        try:
            with db_cursor() as cur:
                cur.execute("""SELECT id, category, message, admin_reply, status, timestamp 
                    FROM ask_corner WHERE submitter_username = %s ORDER BY id DESC LIMIT 20""",
                    (st.session_state.username,))
                my_msgs = cur.fetchall()
            for m_id, cat, msg, rep, stat, ts in my_msgs:
                with st.expander(f"📌 #{m_id} — {cat} [{stat}]"):
                    st.markdown(f"**Message:** {msg}")
                    if rep and rep.strip():
                        st.success(f"**Admin Reply:** {rep}")
        except Exception:
            pass
    
    # ---------- Pricing & Payment ----------
    elif st_nav == T("💳 Pricing & Payment", "💳 Pricing & Payment"):
        st.subheader(T("💳 Pricing & Payment", "💳 Pricing & Payment"))
        full_access_price = get_full_access_price()
        is_full_access = has_full_access(st.session_state.username)
        if is_full_access:
            st.success("✅ You have Full Access!")
        
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"""<div class="price-card">
                <h3>📄 Chapter Exam Set</h3>
                <div class="price-tag">₹19</div>
                <p>Per Set</p></div>""", unsafe_allow_html=True)
        with c2:
            st.markdown(f"""<div class="price-card">
                <h3>🎯 Final Mock Test</h3>
                <div class="price-tag">₹49</div>
                <p>Per Set</p></div>""", unsafe_allow_html=True)
        with c3:
            st.markdown(f"""<div class="price-card">
                <h3>💡 Board Suggestions</h3>
                <div class="price-tag">₹69</div>
                <p>Per Set</p></div>""", unsafe_allow_html=True)
        
        st.markdown("<br/>", unsafe_allow_html=True)
        st.markdown(f"""<div class="price-card-premium">
            <h3>👑 FULL ACCESS — সব Question Unlock</h3>
            <div class="price-tag-premium">₹{full_access_price}</div>
            <p><strong>MCQ + SAQ + 2/3/5 Marks + Map Pointing</strong></p>
        </div>""", unsafe_allow_html=True)
        
        st.markdown("---")
        upi_id = get_upi_id()
        col_qr, col_info = st.columns([1, 1])
        with col_qr:
            st.markdown("#### 📱 Scan & Pay")
            try:
                st.image("payment_qr.png", width=280, caption="Shawon Kar UPI QR")
            except Exception:
                st.info(f"**UPI ID:** `{upi_id}`")
            st.markdown(f"**UPI ID:** `{upi_id}`")
        with col_info:
            st.markdown("#### 📋 Steps:")
            st.markdown("""
1. Open bKash/PhonePe/GPay
2. Scan QR or paste UPI ID
3. Send amount
4. Submit UPI Transaction ID
5. Admin verification → unlock
            """)
        
        st.markdown("---")
        st.markdown("### 📝 Payment Submit")
        try:
            with db_cursor() as cur:
                cur.execute("SELECT id, test_type, code_num, price FROM mock_tests WHERE is_published = 1 ORDER BY id DESC")
                available_items = cur.fetchall()
        except Exception:
            available_items = []
        
        item_options = {f"👑 FULL ACCESS (₹{full_access_price})": ("FULL_ACCESS", "FULL_ACCESS", full_access_price)}
        for m in available_items:
            label = f"[{m[1]}] {m[2]} — ₹{m[3] or 0}"
            item_options[label] = (m[0], m[1], m[3] or 0)
        
        sel_item_label = st.selectbox("কোন Item unlock?", ["-- Select --"] + list(item_options.keys()), key="pay_item_sel")
        upi_ref_in = st.text_input("UPI Transaction ID:", key="pay_upi_ref")
        if st.button("📤 Submit Payment", use_container_width=True, key="pay_submit_btn"):
            if sel_item_label == "-- Select --" or not upi_ref_in.strip():
                st.warning("⚠️ Select & enter UPI ref.")
            else:
                m_id, m_type, m_price = item_options[sel_item_label]
                try:
                    with db_cursor() as cur:
                        cur.execute("""INSERT INTO payments (username, user_name, user_role, phone, item_type, item_id, amount, upi_ref, status)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Pending Verification')""",
                            (st.session_state.username, st.session_state.full_name, st.session_state.role,
                             st.session_state.phone, m_type, str(m_id), m_price, upi_ref_in.strip()))
                    st.cache_data.clear()
                    st.success("🎉 Submitted!")
                except Exception as e:
                    st.error(f"Error: {e}")
        
        st.markdown("---")
        try:
            with db_cursor() as cur:
                cur.execute("""SELECT id, item_type, item_id, amount, upi_ref, status, timestamp, admin_note
                    FROM payments WHERE username = %s ORDER BY id DESC""", (st.session_state.username,))
                my_pays = cur.fetchall()
            for p_id, itype, iid, amt, uref, stat, ts, note in my_pays:
                color = {"Approved": "🟢", "Pending Verification": "🟡", "Rejected": "🔴"}.get(stat, "⚪")
                with st.expander(f"{color} #{p_id} — {itype} — ₹{amt} [{stat}]"):
                    st.markdown(f"**UPI Ref:** `{uref}` | **Date:** {ts}")
                    if note:
                        st.info(f"Note: {note}")
        except Exception:
            pass
    
    # ========================================================================
    # STUDENT PORTAL
    # ========================================================================
    elif active_view_role == "student":
        
        if st_nav == T("🏠 Dashboard", "🏠 Dashboard"):
            st.subheader("🏠 Student Dashboard")
            is_full = has_full_access(st.session_state.username)
            colA, colB, colC = st.columns(3)
            colA.metric("📚 Chapters", "6")
            colB.metric("👑 Full Access", "Active" if is_full else "Locked")
            try:
                with db_cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM questions")
                    total_q = cur.fetchone()[0]
            except Exception:
                total_q = 0
            colC.metric("❓ Total Questions", total_q)
            
            if is_full:
                st.success("👑 Full Access Active!")
            else:
                st.info("💡 ₹100 দিয়ে Full Access কিনুন।")
        
        elif st_nav == T("📖 Practice Center", "📖 Practice Center"):
            st.subheader("📖 Practice Center")
            topic_dict = {t[1]: t[0] for t in cached_topics()}
            if not topic_dict:
                st.warning("No chapters.")
                st.stop()
            selected_topic_name = st.selectbox("Select Chapter:", list(topic_dict.keys()), key="std_topic_sel")
            target_t_id = topic_dict[selected_topic_name]
            all_questions = cached_questions_for_topic(target_t_id)
            
            if not all_questions:
                st.info("No questions in this chapter.")
            else:
                def get_qtype(q):
                    if len(q) > 21 and q[21]:
                        return q[21]
                    if q[16] == 1 and (q[3] or q[4]):
                        return "MCQ"
                    if q[16] == 1:
                        return "SAQ"
                    return "Broad"
                
                mcq_list = [q for q in all_questions if get_qtype(q) == "MCQ"]
                saq_list = [q for q in all_questions if get_qtype(q) == "SAQ"]
                q2_list = [q for q in all_questions if q[16] == 2]
                q3_list = [q for q in all_questions if q[16] == 3]
                q5_list = [q for q in all_questions if q[16] == 5 or q[16] > 3]
                
                t_mcq, t_saq, t2, t3, t5 = st.tabs([
                    f"📝 MCQ ({len(mcq_list)})", f"✏️ SAQ ({len(saq_list)})",
                    f"📘 2 Marks ({len(q2_list)})", f"📗 3 Marks ({len(q3_list)})",
                    f"📕 5 Marks ({len(q5_list)})"
                ])
                
                def render_ask(q_id, idx):
                    try:
                        with db_cursor() as cur:
                            cur.execute("""SELECT status, teacher_answer FROM student_doubts 
                                WHERE student_username = %s AND question_id = %s ORDER BY id DESC LIMIT 1""",
                                (st.session_state.username, q_id))
                            d_row = cur.fetchone()
                    except Exception:
                        d_row = None
                    
                    if d_row and d_row[0] == "Approved" and d_row[1] and d_row[1].strip():
                        st.success("✅ Solution Unlocked!")
                        st.markdown(f"**Answer:**\n\n{d_row[1]}")
                    elif d_row and d_row[0] in ["Pending Admin Assignment", "Assigned to Teacher", "Teacher Submitted (Pending Admin Approval)"]:
                        st.info(f"⏳ {d_row[0]}")
                    else:
                        if st.button(f"🙋 Ask Admin (Q{idx})", key=f"ask_{q_id}", use_container_width=True):
                            try:
                                with db_cursor() as cur:
                                    cur.execute("""INSERT INTO student_doubts (student_username, student_name, question_id, status)
                                        VALUES (%s, %s, %s, 'Pending Admin Assignment')""",
                                        (st.session_state.username, st.session_state.full_name, q_id))
                                st.success("🎉 Sent!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                
                with t_mcq:
                    for idx, q in enumerate(mcq_list, 1):
                        (q_id, q_bn, q_en, oa_bn, oa_en, ob_bn, ob_en, oc_bn, oc_en, od_bn, od_en,
                         corr_opt, expl_bn, expl_en, diff, is_desc, m_val, m_ans_bn, m_ans_en, ms_bn, ms_en, qtype) = q
                        q_label = get_q_text(q_bn, q_en)
                        st.markdown(f"""<div class="card-short">
                            <span style="background-color: #2563eb; color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; float: right;">MCQ</span>
                            <h4>Q{idx}. {q_label}</h4></div>""", unsafe_allow_html=True)
                        opts = [f"A) {get_q_text(oa_bn, oa_en)}", f"B) {get_q_text(ob_bn, ob_en)}",
                                f"C) {get_q_text(oc_bn, oc_en)}", f"D) {get_q_text(od_bn, od_en)}"]
                        user_ans = st.radio(f"Q{idx}:", opts, index=None, key=f"std_mcq_{q_id}")
                        if user_ans:
                            if user_ans[0] == corr_opt:
                                st.success("✅ Correct!")
                            else:
                                st.error(f"❌ Correct: {corr_opt}")
                            exp_text = get_q_text(expl_bn, expl_en)
                            if exp_text:
                                st.info(f"💡 {exp_text}")
                        st.markdown("<hr/>", unsafe_allow_html=True)
                
                with t_saq:
                    for idx, q in enumerate(saq_list, 1):
                        (q_id, q_bn, q_en, oa_bn, oa_en, ob_bn, ob_en, oc_bn, oc_en, od_bn, od_en,
                         corr_opt, expl_bn, expl_en, diff, is_desc, m_val, m_ans_bn, m_ans_en, ms_bn, ms_en, qtype) = q
                        q_label = get_q_text(q_bn, q_en)
                        st.markdown(f"""<div class="card-short" style="border-left-color: #059669;">
                            <span style="background-color: #059669; color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; float: right;">SAQ</span>
                            <h4>Q{idx}. {q_label}</h4></div>""", unsafe_allow_html=True)
                        with st.expander("👁️ View Answer"):
                            st.markdown(f"**Answer:** {corr_opt}")
                            if expl_bn or expl_en:
                                st.markdown(f"**Explanation:** {get_q_text(expl_bn, expl_en)}")
                        st.markdown("<hr/>", unsafe_allow_html=True)
                
                with t2:
                    for idx, q in enumerate(q2_list, 1):
                        q_id = q[0]
                        q_label = get_q_text(q[1], q[2])
                        st.markdown(f"""<div class="card-broad">
                            <span style="background-color: #7c3aed; color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; float: right;">2 Marks</span>
                            <h4>Q{idx}. {q_label}</h4></div>""", unsafe_allow_html=True)
                        render_ask(q_id, idx)
                        st.markdown("<hr/>", unsafe_allow_html=True)
                
                with t3:
                    for idx, q in enumerate(q3_list, 1):
                        q_id = q[0]
                        q_label = get_q_text(q[1], q[2])
                        st.markdown(f"""<div class="card-broad" style="border-left-color: #16a34a;">
                            <span style="background-color: #16a34a; color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; float: right;">3 Marks</span>
                            <h4>Q{idx}. {q_label}</h4></div>""", unsafe_allow_html=True)
                        render_ask(q_id, idx)
                        st.markdown("<hr/>", unsafe_allow_html=True)
                
                with t5:
                    for idx, q in enumerate(q5_list, 1):
                        q_id = q[0]
                        q_label = get_q_text(q[1], q[2])
                        st.markdown(f"""<div class="card-broad" style="border-left-color: #dc2626;">
                            <span style="background-color: #dc2626; color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; float: right;">5 Marks</span>
                            <h4>Q{idx}. {q_label}</h4></div>""", unsafe_allow_html=True)
                        render_ask(q_id, idx)
                        st.markdown("<hr/>", unsafe_allow_html=True)
        
        elif st_nav == T("❓ My Help / Doubt Requests", "❓ My Help / Doubt Requests"):
            st.subheader("❓ My Doubt Requests")
            try:
                with db_cursor() as cur:
                    cur.execute("""SELECT d.id, q.question_text, q.question_text_en, q.marks, d.status, d.teacher_answer, d.timestamp
                        FROM student_doubts d JOIN questions q ON d.question_id = q.id
                        WHERE d.student_username = %s ORDER BY d.id DESC""", (st.session_state.username,))
                    my_doubts = cur.fetchall()
                for d_id, q_txt_bn, q_txt_en, q_m, status, t_ans, t_stamp in my_doubts:
                    color = "🟢" if status == "Approved" else "🟡"
                    with st.expander(f"{color} #{d_id} [{q_m}M] — {status}"):
                        st.markdown(f"**Q:** {get_q_text(q_txt_bn, q_txt_en)}")
                        if status == "Approved" and t_ans:
                            st.success(f"✅ {t_ans}")
                        else:
                            st.info(f"⏳ {status}")
            except Exception:
                pass
        
        elif st_nav == T("📄 Mock Tests & Suggestions", "📄 Mock Tests & Suggestions"):
            st.subheader("📄 Mock Tests & Suggestions")
            try:
                with db_cursor() as cur:
                    cur.execute("SELECT id, test_type, code_num, file_name, file_data, uploader, price, timestamp FROM mock_tests WHERE is_published = 1 ORDER BY id DESC")
                    mocks = cur.fetchall()
                for m_id, t_type, c_num, f_name, f_data, uploader, price, t_stamp in mocks:
                    has_paid = user_has_purchase(st.session_state.username, t_type, m_id)
                    st.markdown(f"### 📄 `{c_num}` — {t_type}")
                    st.caption(f"{uploader} | ₹{price or 0}")
                    if has_paid:
                        if f_data:
                            st.download_button(f"📥 {c_num}", data=bytes(f_data), file_name=f_name, key=f"dl_{m_id}")
                    else:
                        st.markdown(f"""<div class="lock-box">🔒 ₹{price or 0} payment unlock করুন।</div>""", unsafe_allow_html=True)
                    st.markdown("---")
            except Exception:
                pass
        
        elif st_nav == T("📝 My Exam Submissions", "📝 My Exam Submissions"):
            st.subheader("📝 My Exam Submissions")
            try:
                with db_cursor() as cur:
                    cur.execute("SELECT id, test_type, code_num FROM mock_tests WHERE is_published = 1 ORDER BY id DESC")
                    my_tests = cur.fetchall()
                unlocked = [(m[0], m[1], m[2]) for m in my_tests if user_has_purchase(st.session_state.username, m[1], m[0])]
                if not unlocked:
                    st.warning("First unlock a Mock Test.")
                else:
                    test_opts = {f"[{t[1]}] {t[2]}": t[0] for t in unlocked}
                    sel_test = st.selectbox("Select exam:", list(test_opts.keys()), key="sub_exam_sel")
                    sub_file = st.file_uploader("Answer Sheet", type=["pdf", "jpg", "jpeg", "png"], key="sub_answer_file")
                    if st.button("📤 Submit", use_container_width=True, key="sub_ans_btn"):
                        if sub_file is not None:
                            selected_type = sel_test.split("]")[0].strip("[")
                            f_bytes = sub_file.getvalue()
                            with db_cursor() as cur:
                                cur.execute("""INSERT INTO exam_submissions (student_username, student_name, exam_type, exam_code, answer_file_name, answer_file_data, status)
                                    VALUES (%s, %s, %s, %s, %s, %s, 'Submitted')""",
                                    (st.session_state.username, st.session_state.full_name, selected_type,
                                     sel_test, sub_file.name, f_bytes))
                            st.success("🎉 Submitted!")
                
                st.markdown("---")
                with db_cursor() as cur:
                    cur.execute("""SELECT id, exam_code, submitted_at, status, corrected_file_name, corrected_file_data, admin_note
                        FROM exam_submissions WHERE student_username = %s ORDER BY id DESC""", (st.session_state.username,))
                    my_subs = cur.fetchall()
                for s_id, ecode, sub_at, stat, cfname, cfdata, note in my_subs:
                    with st.expander(f"#{s_id} — {ecode} — {stat}"):
                        if note:
                            st.info(f"Note: {note}")
                        if stat == "Checked & Returned" and cfdata:
                            st.download_button("📥 Download Corrected", data=bytes(cfdata), file_name=cfname or "corrected", key=f"dl_corr_{s_id}")
            except Exception as e:
                st.error(f"Error: {e}")
    
    # ========================================================================
    # TEACHER PORTAL
    # ========================================================================
    elif active_view_role == "teacher":
        if st_nav == T("📥 Assigned Student Doubts", "📥 Assigned Student Doubts"):
            st.subheader("📥 Assigned Doubts")
            try:
                with db_cursor() as cur:
                    cur.execute("""SELECT d.id, d.student_name, q.question_text, q.marks, d.status, d.teacher_answer
                        FROM student_doubts d JOIN questions q ON d.question_id = q.id
                        WHERE d.assigned_teacher_username = %s ORDER BY d.id DESC""", (st.session_state.username,))
                    my_doubts = cur.fetchall()
                for d_id, s_name, q_txt, q_m, status, t_ans in my_doubts:
                    with st.expander(f"#{d_id} [{q_m}M] — {s_name} — {status}"):
                        st.markdown(f"**Q:** {q_txt}")
                        sol_in = st.text_area("Solution:", value=t_ans, key=f"t_sol_{d_id}")
                        if st.button("📤 Submit to Admin", key=f"t_btn_{d_id}"):
                            if sol_in.strip():
                                with db_cursor() as cur:
                                    cur.execute("""UPDATE student_doubts SET teacher_answer = %s, status = 'Teacher Submitted (Pending Admin Approval)' WHERE id = %s""",
                                        (sol_in.strip(), d_id))
                                st.success("✅ Sent!")
                                st.rerun()
            except Exception:
                pass
        
        elif st_nav == T("📖 Question Bank Manager", "📖 Question Bank Manager"):
            st.subheader("📖 Question Bank Manager")
            topic_dict = {t[1]: t[0] for t in cached_topics()}
            if not topic_dict:
                st.error("No chapters."); st.stop()
            sel_topic_name = st.selectbox("Chapter:", list(topic_dict.keys()), key="tch_top")
            target_t_id = topic_dict[sel_topic_name]
            
            tab_man, tab_dups, tab_del = st.tabs(["➕ Manual Upload", "🔍 Duplicate Remover", "📖 Browse & Delete"])
            
            with tab_man:
                q_text_bn = st.text_area("Question (Bengali):", key="tch_q_bn")
                q_en_manual = st.text_input("English Translation (Optional):", key="tch_q_en")
                q_type_choice = st.selectbox("Type:", ["MCQ (1 Mark)", "SAQ (1 Mark)", "2 Marks", "3 Marks", "5 Marks"], key="tch_q_type_sel")
                type_marks_map = {"MCQ (1 Mark)": 1, "SAQ (1 Mark)": 1, "2 Marks": 2, "3 Marks": 3, "5 Marks": 5}
                q_marks = type_marks_map[q_type_choice]
                is_mcq = q_type_choice.startswith("MCQ")
                is_saq = q_type_choice.startswith("SAQ")
                q_en_final = q_en_manual.strip() if q_en_manual.strip() else translate_geo_simple(q_text_bn)
                
                if q_text_bn.strip():
                    match, ratio = check_duplicate_question(q_text_bn, target_t_id)
                    if match:
                        st.warning(f"⚠️ Duplicate ({ratio*100:.1f}%): #{match[0]}")
                
                if is_mcq:
                    c1, c2 = st.columns(2)
                    oa = c1.text_input("A)", key="tch_oa")
                    ob = c2.text_input("B)", key="tch_ob")
                    oc = c1.text_input("C)", key="tch_oc")
                    od = c2.text_input("D)", key="tch_od")
                    co = st.selectbox("Correct:", ["A", "B", "C", "D"], key="tch_co")
                    ex = st.text_area("Explanation:", key="tch_ex")
                    if st.button("💾 Save MCQ", key="tch_save_mcq"):
                        if q_text_bn and oa:
                            try:
                                with db_cursor() as cur:
                                    cur.execute("""INSERT INTO questions (topic_id, question_text, question_text_en, option_a, option_b, option_c, option_d, correct_option, explanation, difficulty, is_descriptive, marks, q_type)
                                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Medium', 0, 1, 'MCQ')""",
                                        (target_t_id, q_text_bn, q_en_final, oa, ob, oc, od, co, ex))
                                st.cache_data.clear()
                                st.success("✅ Added!"); st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                elif is_saq:
                    saq_ans = st.text_area("Answer:", key="tch_saq_ans")
                    saq_ex = st.text_area("Explanation:", key="tch_saq_ex")
                    if st.button("💾 Save SAQ", key="tch_save_saq"):
                        if q_text_bn and saq_ans:
                            try:
                                with db_cursor() as cur:
                                    cur.execute("""INSERT INTO questions (topic_id, question_text, question_text_en, correct_option, explanation, difficulty, is_descriptive, marks, q_type)
                                        VALUES (%s, %s, %s, %s, %s, 'Medium', 0, 1, 'SAQ')""",
                                        (target_t_id, q_text_bn, q_en_final, saq_ans, saq_ex))
                                st.cache_data.clear()
                                st.success("✅ Added!"); st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                else:
                    ma = st.text_area(f"Model Answer ({q_marks}M):", key="tch_ma")
                    ms = st.text_area("Marking Scheme:", key="tch_ms")
                    if st.button(f"💾 Save {q_marks}M", key="tch_save_broad"):
                        if q_text_bn:
                            try:
                                with db_cursor() as cur:
                                    cur.execute("""INSERT INTO questions (topic_id, question_text, question_text_en, difficulty, is_descriptive, marks, model_answer, marking_scheme, q_type)
                                        VALUES (%s, %s, %s, 'Hard', 1, %s, %s, %s, 'Broad')""",
                                        (target_t_id, q_text_bn, q_en_final, q_marks, ma, ms))
                                st.cache_data.clear()
                                st.success("✅ Added!"); st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
            
            with tab_dups:
                if st.button("🔍 Scan Duplicates", key="tch_scan"):
                    try:
                        with db_cursor() as cur:
                            cur.execute("SELECT id, question_text, marks FROM questions WHERE topic_id = %s ORDER BY id ASC", (target_t_id,))
                            all_q = cur.fetchall()
                        if len(all_q) >= 2:
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
                                st.warning(f"⚠️ {len(groups)} Groups found!")
                                for gi, grp in enumerate(groups, 1):
                                    st.markdown(f"**Group #{gi}**")
                                    for q in grp:
                                        c1, c2 = st.columns([5, 1])
                                        c1.markdown(f"#{q[0]} [{q[2]}M]: {q[1][:100]}")
                                        if c2.button(f"🗑️ #{q[0]}", key=f"dup_del_{q[0]}_tch"):
                                            with db_cursor() as cur:
                                                cur.execute("DELETE FROM questions WHERE id = %s", (q[0],))
                                            st.cache_data.clear()
                                            st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
            
            with tab_del:
                try:
                    with db_cursor() as cur:
                        cur.execute("SELECT id, question_text, marks FROM questions WHERE topic_id = %s ORDER BY id DESC", (target_t_id,))
                        q_rows = cur.fetchall()
                    for q_id, q_txt, q_m in q_rows:
                        c1, c2 = st.columns([5, 1])
                        c1.markdown(f"**#{q_id} [{q_m}M]:** {q_txt[:200]}")
                        if c2.button(f"🗑️", key=f"td_{q_id}"):
                            with db_cursor() as cur:
                                cur.execute("DELETE FROM questions WHERE id = %s", (q_id,))
                            st.cache_data.clear()
                            st.rerun()
                except Exception:
                    pass
        
        elif st_nav == T("📝 Check Assigned Answer Sheets", "📝 Check Assigned Answer Sheets"):
            st.subheader("📝 Check Assigned Answer Sheets")
            try:
                with db_cursor() as cur:
                    cur.execute("""SELECT id, student_name, exam_code, answer_file_name, answer_file_data, submitted_at, status
                        FROM exam_submissions 
                        WHERE checker_username = %s AND status IN ('Under Check', 'Teacher Submitted for Admin Review')
                        ORDER BY id ASC""", (st.session_state.username,))
                    subs = cur.fetchall()
                for s_id, s_name, ecode, afname, afdata, sub_at, stat in subs:
                    st.markdown(f"""<div class="assigned-card">
                        <strong>📄 #{s_id} — {s_name}</strong><br/>
                        <small>{ecode} | {stat}</small>
                    </div>""", unsafe_allow_html=True)
                    if afdata:
                        st.download_button("📥 Download Answer Sheet", data=bytes(afdata), file_name=afname, key=f"tch_dl_{s_id}")
                    if stat == "Under Check":
                        corr_file = st.file_uploader("Corrected Copy", type=["pdf", "jpg", "jpeg", "png"], key=f"tch_corr_{s_id}")
                        tch_note = st.text_area("Note:", key=f"tch_note_{s_id}")
                        if st.button("📤 Submit to Admin", key=f"tch_sub_{s_id}"):
                            if corr_file is not None:
                                cf_bytes = corr_file.getvalue()
                                with db_cursor() as cur:
                                    cur.execute("""UPDATE exam_submissions 
                                        SET teacher_corrected_file_name = %s, teacher_corrected_file_data = %s,
                                            teacher_note = %s, teacher_submitted_at = CURRENT_TIMESTAMP,
                                            status = 'Teacher Submitted for Admin Review'
                                        WHERE id = %s""",
                                        (corr_file.name, cf_bytes, tch_note.strip(), s_id))
                                st.success("🎉 Sent!")
                                st.rerun()
                    else:
                        st.success("✅ Submitted!")
                    st.markdown("---")
            except Exception:
                pass
        
        elif st_nav == T("📤 Send Suggestions to Admin", "📤 Send Suggestions to Admin"):
            st.subheader("📤 Send Suggestions to Admin")
            with st.form("teacher_submit_form"):
                sub_type = st.selectbox("Type:", ["Chapter Wise Mock Test", "Final Mock Test", "Board Suggestions"], key="ts_type")
                sub_title = st.text_input("Title:", key="ts_title")
                sub_desc = st.text_area("Details:", key="ts_desc")
                sub_price_sug = st.number_input("Suggested Price (₹):", min_value=0, value=0, key="ts_price")
                sub_file = st.file_uploader("File", type=["pdf", "docx"], key="ts_file")
                if st.form_submit_button("📤 Send to Admin"):
                    if sub_file is not None and sub_title.strip():
                        try:
                            f_bytes = sub_file.getvalue()
                            with db_cursor() as cur:
                                cur.execute("""INSERT INTO teacher_submissions (teacher_username, teacher_name, sub_type, title, description, file_name, file_data, status)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'Pending Admin Review')""",
                                    (st.session_state.username, st.session_state.full_name, sub_type,
                                     sub_title.strip(), sub_desc.strip() + f"\n[Price: ₹{sub_price_sug}]",
                                     sub_file.name, f_bytes))
                            st.success("🎉 Sent!")
                        except Exception as e:
                            st.error(f"Error: {e}")
            
            st.markdown("---")
            try:
                with db_cursor() as cur:
                    cur.execute("SELECT id, sub_type, title, status, admin_note, timestamp FROM teacher_submissions WHERE teacher_username = %s ORDER BY id DESC", (st.session_state.username,))
                    my_subs = cur.fetchall()
                for t_id, stype, title, stat, note, ts in my_subs:
                    with st.expander(f"#{t_id} — {stype} — {title} [{stat}]"):
                        if note:
                            st.info(f"Admin Note: {note}")
            except Exception:
                pass
        
        elif st_nav == T("👨‍🏫 Student Track Records", "👨‍🏫 Student Track Records"):
            st.subheader("👨‍🏫 Student Track Records")
            try:
                with db_cursor() as cur:
                    cur.execute("""SELECT student_name, student_phone, school_name, district, exam_name, topic_name, score, total_questions, percentage, timestamp FROM student_scores ORDER BY timestamp DESC""")
                    scores = cur.fetchall()
                if scores:
                    df = pd.DataFrame(scores, columns=["Name", "Phone", "School", "District", "Exam", "Topic", "Score", "Total", "Pct", "Timestamp"])
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No records.")
            except Exception:
                pass
    
    # ========================================================================
    # ADMIN PORTAL
    # ========================================================================
    elif active_view_role == "admin":
        if st_nav == T("🛡️ User Approvals", "🛡️ User Approvals"):
            st.subheader("🛡️ User Approvals")
            try:
                with db_cursor() as cur:
                    cur.execute("""SELECT id, role, full_name, school_name, class_grade, phone, district, approved FROM users WHERE is_admin = 0 ORDER BY approved ASC, id DESC""")
                    all_u = cur.fetchall()
                if all_u:
                    df_u = pd.DataFrame(all_u, columns=["ID", "Role", "Name", "School", "Class", "Phone", "District", "Approved"])
                    st.dataframe(df_u, use_container_width=True)
                    sel_uid = st.number_input("User ID:", min_value=1, step=1, key="adm_uid")
                    c1, c2 = st.columns(2)
                    if c1.button("✅ Approve", use_container_width=True, key="adm_approve_btn"):
                        with db_cursor() as cur:
                            cur.execute("UPDATE users SET approved = 1 WHERE id = %s", (sel_uid,))
                        st.success("Approved!")
                        st.rerun()
                    if c2.button("🚫 Revoke", use_container_width=True, key="adm_revoke_btn"):
                        with db_cursor() as cur:
                            cur.execute("UPDATE users SET approved = 0 WHERE id = %s", (sel_uid,))
                        st.rerun()
                else:
                    st.info("No users.")
            except Exception as e:
                st.error(f"Error: {e}")
        
        elif st_nav == T("❓ Student Doubt Assignment Hub", "❓ Student Doubt Assignment Hub"):
            st.subheader("❓ Doubt Assignment Hub")
            try:
                with db_cursor() as cur:
                    cur.execute("""SELECT d.id, d.student_name, q.question_text, q.marks, d.assigned_teacher_username, d.teacher_answer, d.status
                        FROM student_doubts d JOIN questions q ON d.question_id = q.id 
                        ORDER BY CASE WHEN d.status = 'Teacher Submitted (Pending Admin Approval)' THEN 0 WHEN d.status = 'Pending Admin Assignment' THEN 1 ELSE 2 END, d.id DESC""")
                    doubts = cur.fetchall()
                    cur.execute("SELECT username, full_name FROM users WHERE role = 'teacher' AND approved = 1")
                    teachers = cur.fetchall()
                teacher_map = {f"{t[1]} ({t[0]})": t[0] for t in teachers}
                
                if doubts:
                    df_d = pd.DataFrame(doubts, columns=["ID", "Student", "Question", "Marks", "Assigned", "Answer", "Status"])
                    st.dataframe(df_d[["ID", "Student", "Question", "Marks", "Status"]], use_container_width=True)
                    
                    sel_d_id = st.number_input("Doubt ID:", min_value=1, step=1, key="adm_did")
                    for d in doubts:
                        if d[0] == sel_d_id:
                            st.markdown(f"### #{d[0]} — {d[1]}")
                            st.markdown(f"**Q:** {d[2]}")
                            st.markdown(f"**Status:** `{d[6]}`")
                            if d[6] == "Pending Admin Assignment":
                                colA, colB = st.columns(2)
                                with colA:
                                    if teacher_map:
                                        sel_t = st.selectbox("Teacher:", list(teacher_map.keys()), key="assign_t")
                                        if st.button("Assign to Teacher"):
                                            with db_cursor() as cur:
                                                cur.execute("UPDATE student_doubts SET assigned_teacher_username = %s, status = 'Assigned to Teacher' WHERE id = %s",
                                                           (teacher_map[sel_t], d[0]))
                                            st.rerun()
                                with colB:
                                    direct_ans = st.text_area("Direct Solution:", key="direct_ans")
                                    if st.button("Solve & Approve"):
                                        if direct_ans.strip():
                                            with db_cursor() as cur:
                                                cur.execute("UPDATE student_doubts SET teacher_answer = %s, status = 'Approved' WHERE id = %s",
                                                           (direct_ans.strip(), d[0]))
                                            st.rerun()
                            elif d[6] == "Teacher Submitted (Pending Admin Approval)":
                                rev = st.text_area("Review & Edit:", value=d[5] or "", key="rev_ans")
                                if st.button("✅ Approve & Unlock"):
                                    with db_cursor() as cur:
                                        cur.execute("UPDATE student_doubts SET teacher_answer = %s, status = 'Approved' WHERE id = %s",
                                                   (rev.strip(), d[0]))
                                    st.rerun()
                            elif d[6] == "Approved":
                                st.success("✅ Already approved.")
                else:
                    st.info("No doubts.")
            except Exception as e:
                st.error(f"Error: {e}")
        
        elif st_nav == T("📖 Question Bank Manager", "📖 Question Bank Manager"):
            st.subheader("📖 Question Bank Manager")
            topic_dict = {t[1]: t[0] for t in cached_topics()}
            if not topic_dict:
                st.error("No chapters."); st.stop()
            sel_topic_name = st.selectbox("Chapter:", list(topic_dict.keys()), key="adm_top")
            target_t_id = topic_dict[sel_topic_name]
            
            tab_ext, tab_man, tab_dups, tab_del = st.tabs([
                "⚡ File/URL Extractor", "➕ Manual Upload", "🔍 Duplicate Remover", "📖 Browse & Delete"
            ])
            
            with tab_ext:
                st.markdown("### 📤 Auto-Extract Engine")
                source_type = st.radio("Source:", ["📄 Manual Text Paste", "📁 PDF / DOCX", "🌐 URL"], key="adm_src")
                extracted_text = ""
                
                if "Manual" in source_type:
                    manual_txt = st.text_area("Paste Here:", height=250, key="adm_manual_paste")
                    if manual_txt.strip():
                        extracted_text = normalize_bengali_text(manual_txt)
                elif "PDF" in source_type:
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
                    st.markdown("#### 📝 Preview:")
                    edited = st.text_area("Review:", value=extracted_text, height=200, key="adm_edit")
                    
                    if detect_mcq_format(edited):
                        st.success("🧠 MCQ format detected!")
                        mcq_parsed = smart_parse_mcq_text(edited)
                        st.info(f"✅ {len(mcq_parsed)} MCQs parsed!")
                        for idx, q in enumerate(mcq_parsed, 1):
                            with st.expander(f"Q{idx}: {q['question'][:80]}..."):
                                st.markdown(f"**Q:** {q['question']}")
                                st.markdown(f"**A)** {q['options']['A']}")
                                st.markdown(f"**B)** {q['options']['B']}")
                                st.markdown(f"**C)** {q['options']['C']}")
                                st.markdown(f"**D)** {q['options']['D']}")
                                st.success(f"✅ Correct: {q['correct']}")
                                if q['explanation']:
                                    st.info(f"📝 {q['explanation']}")
                        
                        if st.button(f"🚀 Save {len(mcq_parsed)} MCQs", key="adm_save_mcq_bulk"):
                            try:
                                with db_cursor() as cur:
                                    for q in mcq_parsed:
                                        cur.execute("""INSERT INTO questions (topic_id, question_text, question_text_en, option_a, option_b, option_c, option_d, correct_option, explanation, difficulty, is_descriptive, marks, q_type)
                                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Medium', 0, 1, 'MCQ')""",
                                            (target_t_id, q['question'], translate_geo_simple(q['question']),
                                             q['options']['A'], q['options']['B'], q['options']['C'], q['options']['D'],
                                             q['correct'], q['explanation']))
                                st.cache_data.clear()
                                st.success(f"🎉 {len(mcq_parsed)} MCQs saved!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                    else:
                        parsed = parse_and_categorize_questions(edited)
                        st.success(f"{len(parsed)} questions parsed!")
                        if st.button("🚀 Save All", key="adm_save_all"):
                            try:
                                with db_cursor() as cur:
                                    for q in parsed:
                                        q_bn = q["question"]
                                        q_en = translate_geo_simple(q_bn)
                                        qtype = 'MCQ' if q["marks"] == 1 else 'Broad'
                                        cur.execute("""INSERT INTO questions (topic_id, question_text, question_text_en, option_a, option_b, option_c, option_d, correct_option, explanation, difficulty, is_descriptive, marks, model_answer, marking_scheme, q_type)
                                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Medium', %s, %s, %s, %s, %s)""",
                                            (target_t_id, q_bn, q_en, q["opt_a"], q["opt_b"], q["opt_c"], q["opt_d"],
                                             q["correct"], q["explanation"], q["is_descriptive"], q["marks"],
                                             q_bn if q["is_descriptive"] else "", f"{q['marks']}M Scheme", qtype))
                                st.cache_data.clear()
                                st.success(f"Saved {len(parsed)}!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
            
            with tab_man:
                q_text_bn = st.text_area("Question (Bengali):", key="adm_q_bn")
                q_en_manual = st.text_input("English Translation (Optional):", key="adm_q_en")
                q_type_choice = st.selectbox("Type:", ["MCQ (1 Mark)", "SAQ (1 Mark)", "2 Marks", "3 Marks", "5 Marks"], key="adm_q_type_sel")
                type_marks_map = {"MCQ (1 Mark)": 1, "SAQ (1 Mark)": 1, "2 Marks": 2, "3 Marks": 3, "5 Marks": 5}
                q_marks = type_marks_map[q_type_choice]
                is_mcq = q_type_choice.startswith("MCQ")
                is_saq = q_type_choice.startswith("SAQ")
                q_en_final = q_en_manual.strip() if q_en_manual.strip() else translate_geo_simple(q_text_bn)
                
                if q_text_bn.strip():
                    match, ratio = check_duplicate_question(q_text_bn, target_t_id)
                    if match:
                        st.warning(f"⚠️ Duplicate ({ratio*100:.1f}%): #{match[0]}")
                
                if is_mcq:
                    c1, c2 = st.columns(2)
                    oa = c1.text_input("A)", key="adm_oa")
                    ob = c2.text_input("B)", key="adm_ob")
                    oc = c1.text_input("C)", key="adm_oc")
                    od = c2.text_input("D)", key="adm_od")
                    co = st.selectbox("Correct:", ["A", "B", "C", "D"], key="adm_co2")
                    ex = st.text_area("Explanation:", key="adm_ex2")
                    if st.button("💾 Save MCQ", key="adm_save_mcq2"):
                        if q_text_bn and oa:
                            try:
                                with db_cursor() as cur:
                                    cur.execute("""INSERT INTO questions (topic_id, question_text, question_text_en, option_a, option_b, option_c, option_d, correct_option, explanation, difficulty, is_descriptive, marks, q_type)
                                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Medium', 0, 1, 'MCQ')""",
                                        (target_t_id, q_text_bn, q_en_final, oa, ob, oc, od, co, ex))
                                st.cache_data.clear()
                                st.success("✅"); st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                elif is_saq:
                    saq_ans = st.text_area("Answer:", key="adm_saq_ans")
                    saq_ex = st.text_area("Explanation:", key="adm_saq_ex")
                    if st.button("💾 Save SAQ", key="adm_save_saq"):
                        if q_text_bn and saq_ans:
                            try:
                                with db_cursor() as cur:
                                    cur.execute("""INSERT INTO questions (topic_id, question_text, question_text_en, correct_option, explanation, difficulty, is_descriptive, marks, q_type)
                                        VALUES (%s, %s, %s, %s, %s, 'Medium', 0, 1, 'SAQ')""",
                                        (target_t_id, q_text_bn, q_en_final, saq_ans, saq_ex))
                                st.cache_data.clear()
                                st.success("✅"); st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                else:
                    ma = st.text_area(f"Model Answer ({q_marks}M):", key="adm_ma2")
                    ms = st.text_area("Marking Scheme:", key="adm_ms2")
                    if st.button(f"💾 Save {q_marks}M", key="adm_save_b"):
                        if q_text_bn:
                            try:
                                with db_cursor() as cur:
                                    cur.execute("""INSERT INTO questions (topic_id, question_text, question_text_en, difficulty, is_descriptive, marks, model_answer, marking_scheme, q_type)
                                        VALUES (%s, %s, %s, 'Hard', 1, %s, %s, %s, 'Broad')""",
                                        (target_t_id, q_text_bn, q_en_final, q_marks, ma, ms))
                                st.cache_data.clear()
                                st.success("✅"); st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
            
            with tab_dups:
                if st.button("🔍 Scan Chapter", key="adm_scan"):
                    try:
                        with db_cursor() as cur:
                            cur.execute("SELECT id, question_text, marks FROM questions WHERE topic_id = %s ORDER BY id ASC", (target_t_id,))
                            all_q = cur.fetchall()
                        if len(all_q) >= 2:
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
                                st.warning(f"⚠️ {len(groups)} Groups!")
                                for gi, grp in enumerate(groups, 1):
                                    st.markdown(f"**Group #{gi}**")
                                    for q in grp:
                                        c1, c2 = st.columns([5, 1])
                                        c1.markdown(f"#{q[0]} [{q[2]}M]: {q[1][:100]}")
                                        if c2.button(f"🗑️ #{q[0]}", key=f"dup_del_{q[0]}_adm"):
                                            with db_cursor() as cur:
                                                cur.execute("DELETE FROM questions WHERE id = %s", (q[0],))
                                            st.cache_data.clear()
                                            st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
            
            with tab_del:
                try:
                    with db_cursor() as cur:
                        cur.execute("SELECT id, question_text, marks FROM questions WHERE topic_id = %s ORDER BY id DESC", (target_t_id,))
                        q_rows = cur.fetchall()
                    for q_id, q_txt, q_m in q_rows:
                        c1, c2 = st.columns([5, 1])
                        c1.markdown(f"**#{q_id} [{q_m}M]:** {q_txt[:200]}")
                        if c2.button(f"🗑️ #{q_id}", key=f"ad_{q_id}"):
                            with db_cursor() as cur:
                                cur.execute("DELETE FROM questions WHERE id = %s", (q_id,))
                            st.cache_data.clear()
                            st.rerun()
                except Exception:
                    pass
        
        elif st_nav == T("📄 Upload Mock Tests & Suggestions", "📄 Upload Mock Tests & Suggestions"):
            st.subheader("📄 Upload Mock Tests")
            t_type = st.radio("Type:", ["Chapter Wise Mock Test", "Final Mock Test", "Board Suggestions"], horizontal=True, key="adm_mt")
            default_price = {"Chapter Wise Mock Test": 19, "Final Mock Test": 49, "Board Suggestions": 69}[t_type]
            price = st.number_input("Price (₹)", min_value=0, value=default_price, step=1, key="adm_mp")
            try:
                with db_cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM mock_tests WHERE test_type = %s", (t_type,))
                    cnt = cur.fetchone()[0]
            except Exception:
                cnt = 0
            prefix = "chapter mock" if t_type == "Chapter Wise Mock Test" else ("final mock" if t_type == "Final Mock Test" else "suggestion")
            auto_code = f"{prefix} - {cnt + 1:03d}"
            st.info(f"Code: `{auto_code}`")
            up_file = st.file_uploader("File", type=["pdf", "docx"], key="adm_mu")
            if st.button("🚀 Publish", key="adm_mpub"):
                if up_file:
                    try:
                        f_bytes = up_file.getvalue()
                        with db_cursor() as cur:
                            cur.execute("""INSERT INTO mock_tests (test_type, code_num, file_name, file_data, uploader, price, is_published)
                                VALUES (%s, %s, %s, %s, %s, %s, 1)""",
                                (t_type, auto_code, up_file.name, f_bytes, st.session_state.full_name, price))
                        st.cache_data.clear()
                        st.success("Published!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
            
            st.markdown("---")
            st.markdown("### 📚 All Published Papers")
            try:
                with db_cursor() as cur:
                    cur.execute("SELECT id, test_type, code_num, uploader, price, timestamp FROM mock_tests ORDER BY id DESC")
                    all_mocks = cur.fetchall()
                for m_id, mt, cn, up, pr, ts in all_mocks:
                    cA, cB = st.columns([5, 1])
                    cA.markdown(f"**#{m_id}** — `{cn}` — {mt} — ₹{pr or 0} — by {up}")
                    if cB.button(f"🗑️ #{m_id}", key=f"del_mock_{m_id}"):
                        with db_cursor() as cur:
                            cur.execute("DELETE FROM mock_tests WHERE id = %s", (m_id,))
                        st.cache_data.clear()
                        st.rerun()
            except Exception:
                pass
        
        elif st_nav == T("📤 Teacher Submissions Review", "📤 Teacher Submissions Review"):
            st.subheader("📤 Teacher Submissions Review")
            try:
                with db_cursor() as cur:
                    cur.execute("""SELECT id, teacher_name, sub_type, title, description, file_name, file_data, status, admin_note, timestamp FROM teacher_submissions ORDER BY CASE WHEN status = 'Pending Admin Review' THEN 0 ELSE 1 END, id DESC""")
                    t_subs = cur.fetchall()
                for t_id, tname, stype, title, desc, fname, fdata, stat, note, ts in t_subs:
                    with st.expander(f"#{t_id} — {tname} — {stype} — {title} [{stat}]"):
                        st.markdown(f"**{desc}**")
                        if fdata:
                            st.download_button("📥 Download", data=bytes(fdata), file_name=fname, key=f"dl_ts_{t_id}")
                        if stat == "Pending Admin Review":
                            admin_note = st.text_input("Note:", key=f"tn_{t_id}")
                            default_price = {"Chapter Wise Mock Test": 19, "Final Mock Test": 49, "Board Suggestions": 69}.get(stype, 19)
                            pub_price = st.number_input("Final Price:", min_value=0, value=default_price, step=1, key=f"tp_{t_id}")
                            colA, colB = st.columns(2)
                            if colA.button("✅ Publish", key=f"ap_{t_id}"):
                                try:
                                    with db_cursor() as cur:
                                        cur.execute("SELECT COUNT(*) FROM mock_tests WHERE test_type = %s", (stype,))
                                        cnt2 = cur.fetchone()[0]
                                        prefix = "chapter mock" if stype == "Chapter Wise Mock Test" else ("final mock" if stype == "Final Mock Test" else "suggestion")
                                        auto_code = f"{prefix} - {cnt2 + 1:03d}"
                                        cur.execute("""INSERT INTO mock_tests (test_type, code_num, file_name, file_data, uploader, price, is_published)
                                            VALUES (%s, %s, %s, %s, %s, %s, 1)""",
                                            (stype, auto_code, fname, bytes(fdata) if fdata else None, f"{tname} (via Teacher)", pub_price))
                                        cur.execute("UPDATE teacher_submissions SET status = 'Published', admin_note = %s WHERE id = %s", (admin_note.strip(), t_id))
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error: {e}")
                            if colB.button("❌ Reject", key=f"rj_{t_id}"):
                                with db_cursor() as cur:
                                    cur.execute("UPDATE teacher_submissions SET status = 'Rejected', admin_note = %s WHERE id = %s", (admin_note.strip(), t_id))
                                st.rerun()
            except Exception:
                pass
        
        elif st_nav == T("💡 Ask Corner Suggestions", "💡 Ask Corner Suggestions"):
            st.subheader("💡 Ask Corner Suggestions")
            try:
                with db_cursor() as cur:
                    cur.execute("SELECT id, submitter_name, submitter_role, category, message, admin_reply, status, timestamp FROM ask_corner ORDER BY id DESC")
                    asks = cur.fetchall()
                for a_id, name, role_s, cat, msg, rep, stat, ts in asks:
                    color = "#16a34a" if stat == "Replied" else "#dc2626"
                    st.markdown(f"""
                        <div class="ask-corner-card" style="border-left-color:{color};">
                        <span style="background:{color};color:white;padding:3px 8px;border-radius:5px;font-size:12px;font-weight:bold;">{stat}</span>
                        <strong style="margin-left:10px;">#{a_id} — {cat}</strong><br/>
                        <small>👤 {name} ({role_s}) — {ts}</small>
                        </div>""", unsafe_allow_html=True)
                    st.markdown(f"**{msg}**")
                    reply_text = st.text_area(f"Reply #{a_id}:", value=rep, key=f"ar_{a_id}", height=100)
                    cA, cB = st.columns(2)
                    if cA.button("📤 Send Reply", key=f"sr_{a_id}"):
                        with db_cursor() as cur:
                            cur.execute("UPDATE ask_corner SET admin_reply = %s, status = 'Replied' WHERE id = %s", (reply_text.strip(), a_id))
                        st.rerun()
                    if cB.button("🗑️ Delete", key=f"da_{a_id}"):
                        with db_cursor() as cur:
                            cur.execute("DELETE FROM ask_corner WHERE id = %s", (a_id,))
                        st.rerun()
                    st.markdown("---")
            except Exception:
                pass
        
        elif st_nav == T("💳 Payment Verifications", "💳 Payment Verifications"):
            st.subheader("💳 Payment Verifications")
            try:
                with db_cursor() as cur:
                    cur.execute("""SELECT id, user_name, user_role, phone, item_type, item_id, amount, upi_ref, status, timestamp, admin_note
                        FROM payments ORDER BY CASE WHEN status='Pending Verification' THEN 0 ELSE 1 END, id DESC""")
                    pays = cur.fetchall()
                for p_id, uname, urole, phone, itype, iid, amt, uref, stat, ts, note in pays:
                    color = {"Approved": "🟢", "Pending Verification": "🟡", "Rejected": "🔴"}.get(stat, "⚪")
                    with st.expander(f"{color} #{p_id} — {uname} ({urole}) — ₹{amt} [{stat}]"):
                        st.markdown(f"**Phone:** {phone} | **Item:** {itype} (ID: {iid})")
                        st.markdown(f"**UPI Ref:** `{uref}` | **Time:** {ts}")
                        if stat == "Pending Verification":
                            adm_note = st.text_input("Note:", key=f"pn_{p_id}")
                            cb1, cb2 = st.columns(2)
                            if cb1.button("✅ Approve", key=f"pa_{p_id}", use_container_width=True):
                                try:
                                    with db_cursor() as cur:
                                        cur.execute("UPDATE payments SET status = 'Approved', approved_at = CURRENT_TIMESTAMP, admin_note = %s WHERE id = %s", (adm_note.strip(), p_id))
                                        cur.execute("""INSERT INTO user_purchases (username, item_type, item_id, payment_id, status) VALUES (%s, %s, %s, %s, 'Active')""", (uname, itype, str(iid), p_id))
                                    st.cache_data.clear()
                                    st.success("✅ Approved!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error: {e}")
                            if cb2.button("❌ Reject", key=f"pr_{p_id}", use_container_width=True):
                                with db_cursor() as cur:
                                    cur.execute("UPDATE payments SET status = 'Rejected', admin_note = %s WHERE id = %s", (adm_note.strip(), p_id))
                                st.cache_data.clear()
                                st.rerun()
            except Exception:
                pass
        
        elif st_nav == T("📝 Exam Answer Sheet Checking", "📝 Exam Answer Sheet Checking"):
            st.subheader("📝 Exam Answer Sheet Checking")
            try:
                with db_cursor() as cur:
                    cur.execute("""SELECT id, student_name, exam_code, answer_file_name, answer_file_data, submitted_at, checker_username, status, admin_note
                        FROM exam_submissions ORDER BY id DESC""")
                    subs = cur.fetchall()
                    cur.execute("SELECT username, full_name FROM users WHERE role = 'teacher' AND approved = 1")
                    teachers = cur.fetchall()
                teacher_map = {f"{t[1]} ({t[0]})": t[0] for t in teachers}
                
                for s_id, sname, ecode, afname, afdata, sub_at, checker, stat, note in subs:
                    with st.expander(f"#{s_id} — {sname} — {ecode} [{stat}]"):
                        if afdata:
                            st.download_button("📥 Download", data=bytes(afdata), file_name=afname, key=f"adm_dl_{s_id}")
                        
                        if stat == "Submitted":
                            colA, colB = st.columns(2)
                            with colA:
                                if teacher_map:
                                    sel_t = st.selectbox("Teacher:", list(teacher_map.keys()), key=f"chk_{s_id}")
                                    if st.button("Assign", key=f"asg_{s_id}"):
                                        with db_cursor() as cur:
                                            cur.execute("UPDATE exam_submissions SET checker_username = %s, status = 'Under Check' WHERE id = %s",
                                                       (teacher_map[sel_t], s_id))
                                        st.rerun()
                            with colB:
                                corr_file = st.file_uploader("Corrected:", type=["pdf", "jpg", "png"], key=f"adm_corr_{s_id}")
                                adm_n = st.text_input("Note:", key=f"adm_n_{s_id}")
                                if st.button("✅ Return to Student", key=f"adm_up_{s_id}"):
                                    if corr_file:
                                        cf_bytes = corr_file.getvalue()
                                        with db_cursor() as cur:
                                            cur.execute("""UPDATE exam_submissions SET corrected_file_name = %s, corrected_file_data = %s, corrected_at = CURRENT_TIMESTAMP, status = 'Checked & Returned', admin_note = %s WHERE id = %s""",
                                                       (corr_file.name, cf_bytes, adm_n.strip(), s_id))
                                        st.rerun()
                        elif stat == "Under Check":
                            st.info(f"⏳ Under check by `{checker}`")
                        elif stat == "Checked & Returned":
                            st.success("✅ Returned.")
                        
                        if st.button("🗑️ Delete", key=f"ds_{s_id}"):
                            with db_cursor() as cur:
                                cur.execute("DELETE FROM exam_submissions WHERE id = %s", (s_id,))
                            st.rerun()
            except Exception:
                pass
        
        elif st_nav == T("📊 Analytics & Track Records", "📊 Analytics & Track Records"):
            st.subheader("📊 Analytics")
            try:
                with db_cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM users")
                    u_count = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM questions")
                    q_count = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM payments WHERE status = 'Approved'")
                    p_count = cur.fetchone()[0]
                    cur.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'Approved'")
                    total_revenue = cur.fetchone()[0]
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("👥 Users", u_count)
                c2.metric("❓ Questions", q_count)
                c3.metric("💳 Payments", p_count)
                c4.metric("💰 Revenue", f"₹{total_revenue}")
            except Exception:
                pass

# FOOTER
st.markdown("""
    <div class="footer-block">
        <h3 style="margin-bottom: 5px; color: #38bdf8 !important;">Prepared by - Shawon Kar, Sukannya Chakraborty</h3>
        <p style="margin: 3px 0; color: #f8fafc !important;">M.Sc. in Geography (University Of Calcutta)</p>
        <p style="margin: 3px 0; color: #94a3b8 !important;">B.Ed. (Baba Saheb Ambedkar Education University)</p>
        <p style="margin: 10px 0 0 0; font-weight: bold; color: #38bdf8 !important;">📞 Ph No - 7001257277</p>
    </div>
""", unsafe_allow_html=True)
