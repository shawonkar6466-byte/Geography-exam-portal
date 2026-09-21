import streamlit as st
import sqlite3
import os
import io
import re
import urllib.request
import urllib.parse
import unicodedata
import pandas as pd
from datetime import datetime, timedelta

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

DB_NAME = "geography_exam.db"

st.set_page_config(
    page_title="WBBSE Geography Portal",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================================
# OFFLINE BENGALI→ENGLISH DICTIONARY (Instant, No API)
# ============================================================================
BN_EN_DICT = {
    # Question words
    "কোনটি": "Which one", "কোন": "Which", "কে": "Who", "কি": "What", "কী": "What",
    "কেন": "Why", "কোথায়": "Where", "কখন": "When", "কিভাবে": "How", "কত": "How many",
    "সর্বপ্রথম": "First", "সর্বপ্রধান": "Most important", "প্রধান": "Main", "মূল": "Main",
    "নাম": "Name", "নাম কি": "What is the name", "কি নামে পরিচিত": "known as",
    "উদাহরণ": "Example", "বিশেষ": "Special", "ভিন্ন": "Different", "একই": "Same",
    # Geography terms
    "ভূগোল": "Geography", "ভূবিজ্ঞান": "Geology", "ভূগর্ভ": "Underground",
    "ভূমিরূপ": "Landform", "ভূমিকম্প": "Earthquake", "সুনামি": "Tsunami",
    "বহির্জাত": "Exogenic", "অন্তর্জাত": "Endogenic", "প্রক্রিয়া": "Process",
    "পর্যায়ন": "Gradation", "অবক্ষয়": "Weathering", "ক্ষয়": "Erosion",
    "নদী": "River", "নদ": "River", "বদ্বীপ": "Delta", "জলপ্রপাত": "Waterfall",
    "হিমবাহ": "Glacier", "হিম": "Ice", "বায়ু": "Wind", "বাতাস": "Wind",
    "সমুদ্র": "Sea", "সাগর": "Sea", "মহাসাগর": "Ocean", "উপকূল": "Coast",
    "পাহাড়": "Mountain", "পর্বত": "Mountain", "মালভূমি": "Plateau",
    "সমভূমি": "Plain", "উপত্যকা": "Valley", "গিরিখাত": "Canyon",
    "বায়ুমণ্ডল": "Atmosphere", "বারিমণ্ডল": "Hydrosphere", "জীবমণ্ডল": "Biosphere",
    "স্থলমণ্ডল": "Lithosphere", "জলবায়ু": "Climate", "আবহাওয়া": "Weather",
    "তাপমাত্রা": "Temperature", "বৃষ্টিপাত": "Rainfall", "চাপ": "Pressure",
    "বায়ুপ্রবাহ": "Wind flow", "মৌসুমি": "Monsoon", "বর্ষা": "Monsoon",
    "শীত": "Winter", "গ্রীষ্ম": "Summer", "গ্রীষ্মকাল": "Summer season",
    "আর্দ্রতা": "Humidity", "বাষ্পীভবন": "Evaporation", "ঘনীভবন": "Condensation",
    "বর্জ্য": "Waste", "ব্যবস্থাপনা": "Management", "আবর্জনা": "Garbage",
    "দূষণ": "Pollution", "পরিবেশ": "Environment", "পরিস্থিতি": "Situation",
    "ভারত": "India", "বাংলাদেশ": "Bangladesh", "পশ্চিমবঙ্গ": "West Bengal",
    "কলকাতা": "Kolkata", "দিল্লি": "Delhi", "মুম্বাই": "Mumbai",
    "হিমালয়": "Himalaya", "গঙ্গা": "Ganga", "ব্রহ্মপুত্র": "Brahmaputra",
    "সতলুজ": "Sutlej", "যমুনা": "Yamuna", "দামোদর": "Damodar",
    "উপগ্রহ": "Satellite", "চিত্র": "Image", "মানচিত্র": "Map",
    "ভূ-বৈচিত্র্যসূচক": "Topographical", "টোপোগ্রাফিক্যাল": "Topographical",
    "স্কেল": "Scale", "দিক": "Direction", "উচ্চতা": "Height", "গভীরতা": "Depth",
    "অক্ষরেখা": "Latitude", "দ্রাঘিমারেখা": "Longitude", "নিরক্ষরেখা": "Equator",
    "মেরু": "Pole", "উত্তর": "North", "দক্ষিণ": "South", "পূর্ব": "East", "পশ্চিম": "West",
    # Adjectives/Adverbs
    "প্রথম": "First", "দ্বিতীয়": "Second", "তৃতীয়": "Third", "শেষ": "Last",
    "বড়": "Big", "ছোট": "Small", "উচ্চ": "High", "নিচু": "Low",
    "নতুন": "New", "পুরনো": "Old", "সর্বোচ্চ": "Highest", "সর্বনিম্ন": "Lowest",
    "সঠিক": "Correct", "ভুল": "Wrong", "সম্পূর্ণ": "Complete", "অসম্পূর্ণ": "Incomplete",
    "প্রাকৃতিক": "Natural", "কৃত্রিম": "Artificial", "মানবসৃষ্ট": "Man-made",
    "জীব": "Living", "প্রাণী": "Animal", "উদ্ভিদ": "Plant", "মানুষ": "Human",
    # Prepositions/Connectors
    "থেকে": "from", "দ্বারা": "by", "জন্য": "for", "সাথে": "with", "মধ্যে": "in",
    "উপর": "on", "নিচে": "below", "পরে": "after", "আগে": "before",
    "এবং": "and", "বা": "or", "কিন্তু": "but", "তবে": "however",
    # Common phrases
    "নিচের কোনটি": "Which of the following", "নিম্নলিখিত": "Following",
    "ব্যাখ্যা করুন": "Explain", "বর্ণনা করুন": "Describe",
    "সংক্ষেপে": "Briefly", "উদাহরণ দিন": "Give example",
    "এর প্রভাব": "Its effect", "এর ফলে": "As a result of",
    "ব্যবহার করেন": "used", "আবিষ্কার করেন": "discovered",
    "প্রতিষ্ঠা করেন": "established", "গবেষণা": "Research",
    "তত্ত্ব": "Theory", "সূত্র": "Formula", "নীতি": "Principle",
    "শব্দটি": "The word", "শব্দ": "Word", "অর্থ": "Meaning",
    "প্রথম কে": "Who first", "কার": "Whose", "কোথায় অবস্থিত": "located at",
}

def translate_geo_simple(bn_text):
    """Fast offline Bengali→English translation using dictionary + term replacement"""
    if not bn_text:
        return ""
    if not isinstance(bn_text, str):
        return str(bn_text)
    
    # If no Bengali chars, return as-is
    bn_count = sum(1 for c in bn_text if '\u0980' <= c <= '\u09FF')
    if bn_count < 2:
        return bn_text
    
    result = bn_text
    # Longest-match first (to avoid partial replacements)
    sorted_keys = sorted(BN_EN_DICT.keys(), key=len, reverse=True)
    for bn in sorted_keys:
        if bn in result:
            result = result.replace(bn, " " + BN_EN_DICT[bn] + " ")
    
    # Cleanup multiple spaces
    result = re.sub(r'\s+', ' ', result).strip()
    
    # If still heavily Bengali, mark
    remaining_bn = sum(1 for c in result if '\u0980' <= c <= '\u09FF')
    if remaining_bn > 3:
        # Return original with translation note
        return f"[EN] {result}"
    return result

# ============================================================================
# HELPERS
# ============================================================================
def get_connection():
    try:
        os.makedirs(os.path.dirname(DB_NAME), exist_ok=True)
    except Exception:
        pass
    return sqlite3.connect(DB_NAME, timeout=30)

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

def safe_add_column(cursor, table_name, column_name, column_def):
    try:
        cursor.execute(f"PRAGMA table_info({table_name})")
        cols = [row[1] for row in cursor.fetchall()]
        if column_name not in cols:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
    except Exception:
        pass

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
        q_type TEXT DEFAULT 'MCQ',
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
        file_name TEXT, file_data BLOB, uploader TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS system_settings (
        key TEXT PRIMARY KEY, value TEXT)""")
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
    cursor.execute("""CREATE TABLE IF NOT EXISTS exam_submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_username TEXT,
        student_name TEXT, exam_type TEXT, exam_code TEXT,
        answer_file_name TEXT, answer_file_data BLOB,
        submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        checker_username TEXT DEFAULT '', status TEXT DEFAULT 'Submitted',
        corrected_file_name TEXT DEFAULT '', corrected_file_data BLOB,
        corrected_at DATETIME, admin_note TEXT DEFAULT '')""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS teacher_submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, teacher_username TEXT,
        teacher_name TEXT, sub_type TEXT, title TEXT, description TEXT,
        file_name TEXT, file_data BLOB,
        status TEXT DEFAULT 'Pending Admin Review',
        admin_note TEXT DEFAULT '',
        published_mock_id INTEGER DEFAULT 0,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    
    safe_add_column(cursor, 'mock_tests', 'price', 'INTEGER DEFAULT 0')
    safe_add_column(cursor, 'mock_tests', 'is_published', 'INTEGER DEFAULT 1')
    safe_add_column(cursor, 'questions', 'q_type', "TEXT DEFAULT 'MCQ'")
    safe_add_column(cursor, 'exam_submissions', 'teacher_corrected_file_name', 'TEXT DEFAULT ""')
    safe_add_column(cursor, 'exam_submissions', 'teacher_corrected_file_data', 'BLOB')
    safe_add_column(cursor, 'exam_submissions', 'teacher_note', 'TEXT DEFAULT ""')
    safe_add_column(cursor, 'exam_submissions', 'teacher_submitted_at', 'DATETIME')
    
    cursor.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('portal_url', 'https://geography-exam-app.streamlit.app')")
    cursor.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('upi_id', 'shawonkar6466-1@oksbi')")
    cursor.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('full_access_price', '100')")
    
    cursor.execute("INSERT OR IGNORE INTO exams (id, name, description) VALUES (1, 'Madhyamik Class 10', 'WBBSE Class 10 Geography')")
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

ADMIN_PASSCODE = "admin123"

# ============================================================================
# LANGUAGE / TRANSLATION
# ============================================================================
def T(bn, en):
    lang = st.session_state.get('language', 'Bengali')
    return bn if lang == "Bengali" else en

def get_q_text(bn_text, en_text):
    """Return question text — fast, no API calls"""
    lang = st.session_state.get('language', 'Bengali')
    if lang == "Bengali":
        return bn_text or en_text or ""
    # English mode
    if en_text and en_text.strip():
        return en_text
    if bn_text:
        # Use offline dictionary
        return translate_geo_simple(bn_text)
    return ""

# ============================================================================
# CACHED FUNCTIONS
# ============================================================================
@st.cache_data(ttl=60, show_spinner=False)
def cached_topics():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM topics ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return rows

@st.cache_data(ttl=15, show_spinner=False)
def cached_has_purchase(username, item_type, item_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT COUNT(*) FROM user_purchases
        WHERE username = ? AND item_type = ? AND item_id = ? AND status = 'Active'""",
        (username, item_type, str(item_id)))
    cnt = cursor.fetchone()[0]
    conn.close()
    return cnt > 0

@st.cache_data(ttl=30, show_spinner=False)
def cached_questions_for_topic(topic_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT id, question_text, question_text_en, option_a, option_a_en, option_b, option_b_en,
        option_c, option_c_en, option_d, option_d_en, correct_option, explanation, explanation_en,
        difficulty, is_descriptive, marks, model_answer, model_answer_en, marking_scheme, marking_scheme_en, q_type
        FROM questions WHERE topic_id = ?""", (topic_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

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
    return bool(re.search(r'^[\(\[]?\s*[কখঘগ]\s*[\)\]]', text, re.MULTILINE))

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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, question_text FROM questions WHERE topic_id = ?", (topic_id,))
    existing_qs = cursor.fetchall()
    conn.close()
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

def get_full_access_price():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM system_settings WHERE key = 'full_access_price'")
    row = cursor.fetchone()
    conn.close()
    return int(row[0]) if row else 100

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
    [data-testid="stSidebar"], [data-testid="stSidebar"] > div {
        background-color: #ffffff !important;
    }
    [data-testid="stSidebar"] * { color: #0f172a !important; }
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
    .stTabs [data-baseweb="tab"] { background-color: transparent !important; color: #475569 !important; font-weight: 600 !important; border-radius: 8px !important; }
    .stTabs [aria-selected="true"] { background-color: #ffffff !important; color: #1d4ed8 !important; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
    .stButton > button, .stDownloadButton > button {
        background-color: #2563eb !important; color: #ffffff !important;
        border: none !important; border-radius: 8px !important;
        font-weight: 700 !important; padding: 10px 18px !important;
    }
    .stButton > button:hover { background-color: #1d4ed8 !important; }
    .stButton > button p, .stDownloadButton > button p { color: #ffffff !important; }
    [data-testid="stForm"] { background-color: #ffffff !important; border: 1.5px solid #cbd5e1 !important; border-radius: 12px !important; padding: 20px !important; }
    [data-testid="stMetric"] { background-color: #ffffff !important; padding: 16px !important; border-radius: 12px !important; border: 1.5px solid #cbd5e1 !important; }
    [data-testid="stMetricValue"], [data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * { color: #0f172a !important; }
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
        border-top: 1.5px solid #cbd5e1; border-right: 1.5px solid #cbd5e1; border-bottom: 1.5px solid #cbd5e1;
    }
    .card-short h4 { color: #000000 !important; font-weight: 900 !important; font-size: 1.15rem !important; }
    
    .card-broad {
        background-color: #ffffff !important; color: #000000 !important;
        padding: 22px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        border-left: 6px solid #7c3aed; margin-bottom: 18px;
        border-top: 1.5px solid #cbd5e1; border-right: 1.5px solid #cbd5e1; border-bottom: 1.5px solid #cbd5e1;
    }
    .card-broad h4 { color: #000000 !important; font-weight: 900 !important; }
    
    .price-card {
        background: linear-gradient(135deg, #ffffff 0%, #eff6ff 100%);
        padding: 22px; border-radius: 14px; text-align: center;
        border: 2px solid #2563eb; margin-bottom: 15px;
        box-shadow: 0 6px 18px rgba(37,99,235,0.12);
    }
    .price-card h3 { color: #1e3a8a !important; margin: 0 0 8px 0; font-size: 1.3rem !important; }
    .price-card p { color: #475569 !important; }
    .price-tag { font-size: 2.2rem; font-weight: 900; color: #059669 !important; margin: 10px 0; }
    
    .price-card-premium {
        background: linear-gradient(135deg, #fef3c7 0%, #fde68a 50%, #fcd34d 100%);
        padding: 26px; border-radius: 14px; text-align: center;
        border: 3px solid #f59e0b; margin-bottom: 15px;
        box-shadow: 0 8px 22px rgba(245,158,11,0.25);
    }
    .price-card-premium h3 { color: #78350f !important; margin: 0 0 8px 0; font-size: 1.4rem !important; }
    .price-card-premium p { color: #92400e !important; }
    .price-tag-premium { font-size: 2.6rem; font-weight: 900; color: #b45309 !important; margin: 12px 0; }
    
    .footer-block {
        background-color: #0f172a; color: #f8fafc; padding: 28px;
        border-radius: 14px; text-align: center; margin-top: 50px;
        border-top: 5px solid #2563eb;
    }
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
            <p>WBBSE Class 10 Geography & Environment — Official Syllabus Practice Hub</p>
        </div>""", unsafe_allow_html=True)

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
                            st.warning(T("⚠️ Admin approval pending.", "⚠️ Admin approval pending."))
                    else:
                        st.error(T("❌ Wrong Password.", "❌ Wrong Password."))
                else:
                    st.error(T("❌ Account not found.", "❌ Account not found."))
    
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
            st.success(f"🎁 {T('Referral detected', 'Referral detected')}: `{ref_default_s}`")
        s_ref = st.text_input(T("Referral Code (Optional)", "Referral Code (Optional)"), value=ref_default_s, key="s_ref")
        
        if st.button(T("Submit Student Registration", "Submit Student Registration"), use_container_width=True, key="student_reg_submit_btn"):
            if s_name and s_school and s_phone and s_pass:
                try:
                    conn = get_connection()
                    cursor = conn.cursor()
                    auto_ref = f"GEO-REF-{s_phone[-4:] if len(s_phone) >= 4 else '10'}"
                    cursor.execute("""INSERT INTO users 
                        (username, password, role, full_name, school_name, class_grade, phone, district, approved, is_admin, referral_code)
                        VALUES (?, ?, 'student', ?, ?, ?, ?, ?, 0, 0, ?)""",
                        (s_phone, s_pass, s_name, s_school, s_class, s_phone, s_dist, auto_ref))
                    if s_ref.strip():
                        cursor.execute("UPDATE users SET referral_count = referral_count + 1 WHERE referral_code = ?", (s_ref.strip(),))
                    conn.commit()
                    conn.close()
                    st.success(T("🎉 Registration requested!", "🎉 Registration requested!"))
                except sqlite3.IntegrityError:
                    st.error(T("❌ Account exists.", "❌ Account already exists."))
            else:
                st.error(T("⚠️ Fill all fields.", "⚠️ Fill all required fields."))
    
    with tab_teacher_reg:
        st.subheader(T("New Teacher Registration", "New Teacher Registration"))
        t_name = st.text_input(T("Name", "Name"), key="t_name")
        t_school = st.text_input(T("School", "School"), key="t_sch")
        t_phone = st.text_input(T("Phone", "Phone"), key="t_ph")
        t_dist = st.text_input(T("District", "District"), key="t_dist")
        t_pass = st.text_input(T("Password", "Password"), type="password", key="t_pass")
        
        ref_default_t = st.session_state.get('referred_by', '')
        if ref_default_t:
            st.success(f"🎁 {T('Referral detected', 'Referral detected')}: `{ref_default_t}`")
        t_ref = st.text_input(T("Referral Code (Optional)", "Referral Code (Optional)"), value=ref_default_t, key="t_ref")
        
        if st.button(T("Submit Teacher Registration", "Submit Teacher Registration"), use_container_width=True, key="teacher_reg_submit_btn"):
            if t_name and t_school and t_phone and t_pass:
                try:
                    conn = get_connection()
                    cursor = conn.cursor()
                    auto_t_ref = f"GEO-REF-T{t_phone[-4:] if len(t_phone) >= 4 else '99'}"
                    cursor.execute("""INSERT INTO users 
                        (username, password, role, full_name, school_name, class_grade, phone, district, approved, is_admin, referral_code)
                        VALUES (?, ?, 'teacher', ?, ?, 'Faculty', ?, ?, 0, 0, ?)""",
                        (t_phone, t_pass, t_name, t_school, t_phone, t_dist, auto_t_ref))
                    if t_ref.strip():
                        cursor.execute("UPDATE users SET referral_count = referral_count + 1 WHERE referral_code = ?", (t_ref.strip(),))
                    conn.commit()
                    conn.close()
                    st.success(T("🎉 Registration requested!", "🎉 Registration requested!"))
                except sqlite3.IntegrityError:
                    st.error(T("❌ Account exists.", "❌ Account already exists."))
            else:
                st.error(T("⚠️ Fill all fields.", "⚠️ Fill all required fields."))

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
        st.sidebar.markdown(T("👑 **Admin Super-Control**", "👑 **Admin Super-Control**"))
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
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""SELECT COUNT(*) FROM exam_submissions 
            WHERE checker_username = ? AND status = 'Under Check'""", (st.session_state.username,))
        teacher_has_assignments = cursor.fetchone()[0] > 0
        conn.close()
    
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
    
    # ---------- Madhyamik Drive Papers ----------
    if st_nav == T("📁 Madhyamik Drive Papers", "📁 Madhyamik Drive Papers"):
        st.subheader(T("📁 Official Madhyamik Google Drive Papers", "📁 Official Madhyamik Google Drive Papers"))
        st.markdown(f"""
            <div style="background-color: #eff6ff; border: 2px solid #2563eb; padding: 22px; border-radius: 12px; margin-bottom: 20px;">
                <h3 style="color: #1e3a8a; margin-top:0;">📥 {T('Official Madhyamik Board Question Papers', 'Official Madhyamik Board Question Papers')}</h3>
                <p style="color: #0f172a;">{T('২০১৭ থেকে ২০২৬ সালের সব অফিশিয়াল মাধ্যমিক ভূগোল প্রশ্নপত্র:', 'All official Madhyamik Geography papers from 2017 to 2026:')}</p>
                <a href="https://drive.google.com/drive/folders/1q4cLE5sYcjElqSnZPQ4Tx4lkbrB-U-pj?usp=drive_link" target="_blank" style="background-color: #2563eb; color: white; padding: 10px 20px; border-radius: 8px; text-decoration: none; font-weight: bold; display: inline-block;">🔗 Open Google Drive Folder</a>
            </div>""", unsafe_allow_html=True)
    
    # ---------- Share & Referral ----------
    elif st_nav == T("🎁 Share & Referral Links", "🎁 Share & Referral Links"):
        st.subheader(T("🎁 Refer Friends & Share Portal", "🎁 Refer Friends & Share Portal"))
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT referral_code, referral_count FROM users WHERE username = ?", (st.session_state.username,))
        ref_row = cursor.fetchone()
        current_portal_url = get_portal_url()
        my_code = ref_row[0] if ref_row and ref_row[0] else "GEO-REF-10"
        my_count = ref_row[1] if ref_row and ref_row[1] else 0
        
        if role == "admin":
            st.markdown(f"#### 🌐 {T('Portal URL Configuration', 'Portal URL Configuration')}")
            new_url_val = st.text_input(T("Official Web Link:", "Official Web Link:"), value=current_portal_url, key="adm_portal_url")
            if st.button(T("💾 Save Portal URL", "💾 Save Portal URL"), key="save_portal_url_btn"):
                cursor.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('portal_url', ?)", (new_url_val.strip(),))
                conn.commit()
                st.success("✅ Updated!")
                st.rerun()
        conn.close()
        
        col1, col2 = st.columns(2)
        col1.metric(T("Your Referral Code", "Your Referral Code"), my_code)
        col2.metric(T("Successful Referrals", "Successful Referrals"), f"{my_count} / 100")
        st.progress(min(my_count / 100.0, 1.0))
        if my_count >= 100:
            st.balloons()
            st.success(T("🎉 100 referrals!", "🎉 100 referrals!"))
        else:
            st.info(T(f"💡 {100 - my_count} more for Certificate!", f"💡 {100 - my_count} more for Certificate!"))
        
        ref_link = f"{current_portal_url}?ref={my_code}"
        share_msg = f"🌍 Join WBBSE Class 10 Geography Portal!\n\n📚 Practice Sets, PYQs, Mock Tests & Doubt Solving\n\n👉 Click here: {ref_link}\n\n🔑 Your referral code: {my_code}\n\n(Use my code during signup!)"
        encoded_msg = urllib.parse.quote(share_msg)
        
        col_wa, col_sms, col_fb = st.columns(3)
        col_wa.markdown(f'<a href="https://api.whatsapp.com/send?text={encoded_msg}" target="_blank" style="background-color:#22c55e; color:white; padding:10px 16px; border-radius:8px; text-decoration:none; font-weight:bold; display:block; text-align:center;">📱 WhatsApp</a>', unsafe_allow_html=True)
        col_sms.markdown(f'<a href="sms:?body={encoded_msg}" style="background-color:#0284c7; color:white; padding:10px 16px; border-radius:8px; text-decoration:none; font-weight:bold; display:block; text-align:center;">💬 SMS</a>', unsafe_allow_html=True)
        col_fb.markdown(f'<a href="https://www.facebook.com/sharer/sharer.php?u={urllib.parse.quote(ref_link)}&quote={encoded_msg}" target="_blank" style="background-color:#1d4ed8; color:white; padding:10px 16px; border-radius:8px; text-decoration:none; font-weight:bold; display:block; text-align:center;">📘 Facebook</a>', unsafe_allow_html=True)
        
        st.text_area("", value=share_msg, height=140, key="share_text_area", label_visibility="collapsed")
    
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
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute("""INSERT INTO ask_corner (submitter_username, submitter_name, submitter_role, category, message)
                        VALUES (?, ?, ?, ?, ?)""",
                        (st.session_state.username, st.session_state.full_name, st.session_state.role, ask_cat, ask_msg.strip()))
                    conn.commit()
                    conn.close()
                    st.success(T("🎉 Sent!", "🎉 Sent!"))
        
        st.markdown("---")
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""SELECT id, category, message, admin_reply, status, timestamp 
            FROM ask_corner WHERE submitter_username = ? ORDER BY id DESC LIMIT 20""",
            (st.session_state.username,))
        my_msgs = cursor.fetchall()
        conn.close()
        for m_id, cat, msg, rep, stat, ts in my_msgs:
            with st.expander(f"📌 #{m_id} — {cat} [{stat}]"):
                st.markdown(f"**{T('Message', 'Message')}:** {msg}")
                if rep and rep.strip():
                    st.success(f"**{T('Admin Reply', 'Admin Reply')}:** {rep}")
    
    # ---------- Pricing & Payment ----------
    elif st_nav == T("💳 Pricing & Payment", "💳 Pricing & Payment"):
        st.subheader(T("💳 Pricing & Payment", "💳 Pricing & Payment"))
        
        full_access_price = get_full_access_price()
        is_full_access = has_full_access(st.session_state.username)
        
        if is_full_access:
            st.success(T("✅ আপনি Full Access কিনেছেন!", "✅ You have Full Access!"))
        
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"""<div class="price-card">
                <h3>📄 {T('Chapter Exam Set', 'Chapter Exam Set')}</h3>
                <div class="price-tag">₹19</div>
                <p>{T('প্রতি Set', 'Per Set')}</p></div>""", unsafe_allow_html=True)
        with c2:
            st.markdown(f"""<div class="price-card">
                <h3>🎯 {T('Final Mock Test', 'Final Mock Test')}</h3>
                <div class="price-tag">₹49</div>
                <p>{T('প্রতি Set', 'Per Set')}</p></div>""", unsafe_allow_html=True)
        with c3:
            st.markdown(f"""<div class="price-card">
                <h3>💡 {T('Board Suggestions', 'Board Suggestions')}</h3>
                <div class="price-tag">₹69</div>
                <p>{T('প্রতি Set', 'Per Set')}</p></div>""", unsafe_allow_html=True)
        
        st.markdown("<br/>", unsafe_allow_html=True)
        
        st.markdown(f"""<div class="price-card-premium">
            <h3>👑 {T('FULL ACCESS — সব Question Unlock', 'FULL ACCESS — All Questions')}</h3>
            <div class="price-tag-premium">₹{full_access_price}</div>
            <p style="font-size:1.05em;"><strong>{T('MCQ + SAQ + 2/3/5 Marks + Map Pointing', 'MCQ + SAQ + 2/3/5 Marks + Map Pointing')}</strong></p>
            <p>{T('সব chapter এর সব প্রশ্ন unlock!', 'Unlock ALL questions from ALL chapters!')}</p>
        </div>""", unsafe_allow_html=True)
        
        st.markdown("---")
        
        upi_id = get_upi_id()
        col_qr, col_info = st.columns([1, 1])
        with col_qr:
            st.markdown(f"#### 📱 {T('Scan & Pay', 'Scan & Pay')}")
            try:
                st.image("payment_qr.png", width=280, caption="Shawon Kar UPI QR")
            except Exception:
                st.warning(T("⚠️ payment_qr.png missing.", "⚠️ payment_qr.png missing."))
            st.markdown(f"**UPI ID:** `{upi_id}`")
        with col_info:
            st.markdown(f"#### 📋 {T('Steps:', 'Steps:')}")
            st.markdown(T("""
১. bKash/PhonePe/GPay খুলুন
২. QR scan করুন বা UPI ID paste করুন
৩. Amount পাঠান
৪. UPI Transaction ID submit করুন
৫. Admin verification → unlock
            """, """
1. Open bKash/PhonePe/GPay
2. Scan QR or paste UPI ID
3. Send amount
4. Submit UPI Transaction ID
5. Admin verification → unlock
            """))
        
        st.markdown("---")
        st.markdown(f"### 📝 {T('Payment Submit', 'Payment Submit')}")
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, test_type, code_num, price FROM mock_tests WHERE is_published = 1 ORDER BY id DESC")
        available_items = cursor.fetchall()
        conn.close()
        
        item_options = {T(f"👑 FULL ACCESS (₹{full_access_price})", f"👑 FULL ACCESS (₹{full_access_price})"): ("FULL_ACCESS", "FULL_ACCESS", full_access_price)}
        for m in available_items:
            label = f"[{m[1]}] {m[2]} — ₹{m[3] or 0}"
            item_options[label] = (m[0], m[1], m[3] or 0)
        
        sel_item_label = st.selectbox(T("কোন Item unlock?", "Which item to unlock?"), ["-- Select --"] + list(item_options.keys()), key="pay_item_sel")
        upi_ref_in = st.text_input(T("UPI Transaction ID:", "UPI Transaction ID:"), key="pay_upi_ref")
        if st.button(T("📤 Submit Payment", "📤 Submit Payment"), use_container_width=True, key="pay_submit_btn"):
            if sel_item_label == "-- Select --" or not upi_ref_in.strip():
                st.warning(T("⚠️ Select item & enter UPI ref.", "⚠️ Select item & enter UPI ref."))
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
                st.cache_data.clear()
                st.success(T("🎉 Submitted!", "🎉 Submitted!"))
        
        st.markdown("---")
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""SELECT id, item_type, item_id, amount, upi_ref, status, timestamp, admin_note
            FROM payments WHERE username = ? ORDER BY id DESC""", (st.session_state.username,))
        my_pays = cursor.fetchall()
        conn.close()
        for p_id, itype, iid, amt, uref, stat, ts, note in my_pays:
            color = {"Approved": "🟢", "Pending Verification": "🟡", "Rejected": "🔴"}.get(stat, "⚪")
            with st.expander(f"{color} #{p_id} — {itype} — ₹{amt} [{stat}]"):
                st.markdown(f"**UPI Ref:** `{uref}` | **Date:** {ts}")
                if note:
                    st.info(f"{T('Note', 'Note')}: {note}")
    
    # ========================================================================
    # STUDENT PORTAL
    # ========================================================================
    elif active_view_role == "student":
        
        if st_nav == T("🏠 Dashboard", "🏠 Dashboard"):
            st.subheader(T("🏠 Student Dashboard", "🏠 Student Dashboard"))
            is_full = has_full_access(st.session_state.username)
            
            colA, colB, colC = st.columns(3)
            colA.metric(T("📚 Chapters", "📚 Chapters"), "6")
            colB.metric(T("👑 Full Access", "👑 Full Access"), T("Active", "Active") if is_full else T("Locked", "Locked"))
            
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM questions")
            total_q = cursor.fetchone()[0]
            conn.close()
            colC.metric(T("❓ Total Questions", "❓ Total Questions"), total_q)
            
            if is_full:
                st.success(T("👑 আপনি Full Access User!", "👑 You have Full Access!"))
            else:
                st.info(T("💡 ₹100 দিয়ে Full Access কিনলে সব প্রশ্ন unlock হবে।", "💡 Buy Full Access for ₹100 to unlock all questions."))
            
            st.markdown("---")
            st.markdown(f"### 🔥 {T('Featured Questions', 'Featured Questions')}")
            
            conn = get_connection()
            cursor = conn.cursor()
            topics = cached_topics()
            for t_id, t_name in topics:
                cursor.execute("""SELECT id, question_text, question_text_en, marks FROM questions WHERE topic_id = ? ORDER BY RANDOM() LIMIT 2""", (t_id,))
                qs = cursor.fetchall()
                if qs:
                    st.markdown(f"#### 📖 {t_name}")
                    for q_id, q_bn, q_en, q_m in qs:
                        q_label = get_q_text(q_bn, q_en)
                        unlocked = is_full
                        lock_icon = "🔓" if unlocked else "🔒"
                        with st.expander(f"{lock_icon} [{q_m}M] {q_label[:100]}..."):
                            st.markdown(f"**{T('Question', 'Question')}:** {q_label}")
                            if not unlocked and q_m > 1:
                                st.warning(T("🔒 Full Access কিনুন (₹100)", "🔒 Buy Full Access (₹100)"))
            cursor.close()
            conn.close()
        
        elif st_nav == T("📖 Practice Center", "📖 Practice Center"):
            st.subheader(T("📖 WBBSE Class 10 Geography Practice Center", "📖 WBBSE Class 10 Geography Practice Center"))
            
            topic_dict = {t[1]: t[0] for t in cached_topics()}
            if not topic_dict:
                st.error("⚠️ No chapters.")
                st.stop()
            
            selected_topic_name = st.selectbox(T("Select Chapter:", "Select Chapter:"), list(topic_dict.keys()), key="std_topic_sel")
            target_t_id = topic_dict[selected_topic_name]
            
            all_questions = cached_questions_for_topic(target_t_id)
            
            if not all_questions:
                st.info(T("এই chapter এ প্রশ্ন নেই।", "No questions in this chapter yet."))
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
                    T(f"📝 MCQ ({len(mcq_list)})", f"📝 MCQ ({len(mcq_list)})"),
                    T(f"✏️ SAQ ({len(saq_list)})", f"✏️ SAQ ({len(saq_list)})"),
                    T(f"📘 2 Marks ({len(q2_list)})", f"📘 2 Marks ({len(q2_list)})"),
                    T(f"📗 3 Marks ({len(q3_list)})", f"📗 3 Marks ({len(q3_list)})"),
                    T(f"📕 5 Marks ({len(q5_list)})", f"📕 5 Marks ({len(q5_list)})")
                ])
                
                def render_ask_button(q_id, idx):
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute("""SELECT status, teacher_answer FROM student_doubts 
                        WHERE student_username = ? AND question_id = ? ORDER BY id DESC LIMIT 1""",
                        (st.session_state.username, q_id))
                    d_row = cursor.fetchone()
                    conn.close()
                    
                    if d_row and d_row[0] == "Approved" and d_row[1] and d_row[1].strip():
                        st.success(T("✅ Solution Unlocked!", "✅ Solution Unlocked!"))
                        st.markdown(f"**{T('Model Answer', 'Model Answer')}:**\n\n{d_row[1]}")
                        st.download_button(T("📥 Download", "📥 Download"), data=d_row[1], file_name=f"Solution_Q{q_id}.txt", key=f"dl_{q_id}")
                    elif d_row and d_row[0] in ["Pending Admin Assignment", "Assigned to Teacher", "Teacher Submitted (Pending Admin Approval)"]:
                        st.info(f"⏳ {T('Status', 'Status')}: `{d_row[0]}`")
                    else:
                        if st.button(T(f"🙋 Ask Admin (Q{idx})", f"🙋 Ask Admin (Q{idx})"), key=f"ask_{q_id}", use_container_width=True):
                            conn = get_connection()
                            cursor = conn.cursor()
                            cursor.execute("""SELECT id FROM student_doubts 
                                WHERE student_username = ? AND question_id = ?
                                AND status IN ('Pending Admin Assignment', 'Assigned to Teacher', 'Teacher Submitted (Pending Admin Approval)', 'Approved')""",
                                (st.session_state.username, q_id))
                            exists = cursor.fetchone()
                            if exists:
                                st.warning(T("⚠️ Already requested!", "⚠️ Already requested!"))
                            else:
                                cursor.execute("""INSERT INTO student_doubts (student_username, student_name, question_id, status)
                                    VALUES (?, ?, ?, 'Pending Admin Assignment')""",
                                    (st.session_state.username, st.session_state.full_name, q_id))
                                conn.commit()
                                st.success(T("🎉 Sent!", "🎉 Sent!"))
                                st.rerun()
                            conn.close()
                
                with t_mcq:
                    if not mcq_list:
                        st.info(T("No MCQs.", "No MCQs."))
                    else:
                        for idx, q in enumerate(mcq_list, 1):
                            (q_id, q_bn, q_en, oa_bn, oa_en, ob_bn, ob_en, oc_bn, oc_en, od_bn, od_en,
                             corr_opt, expl_bn, expl_en, diff, is_desc, m_val, m_ans_bn, m_ans_en, ms_bn, ms_en, qtype) = q
                            q_label = get_q_text(q_bn, q_en)
                            st.markdown(f"""<div class="card-short">
                                <span style="background-color: #2563eb; color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; float: right;">MCQ</span>
                                <h4>Q{idx}. {q_label}</h4></div>""", unsafe_allow_html=True)
                            
                            opts = [
                                f"A) {get_q_text(oa_bn, oa_en)}",
                                f"B) {get_q_text(ob_bn, ob_en)}",
                                f"C) {get_q_text(oc_bn, oc_en)}",
                                f"D) {get_q_text(od_bn, od_en)}"
                            ]
                            user_ans = st.radio(T(f"Select Q{idx}:", f"Select Q{idx}:"), opts, index=None, key=f"std_mcq_{q_id}")
                            if user_ans:
                                if user_ans[0] == corr_opt:
                                    st.success(T("✅ Correct!", "✅ Correct!"))
                                else:
                                    st.error(f"❌ {T('Correct', 'Correct')}: {corr_opt}")
                                exp_text = get_q_text(expl_bn, expl_en)
                                if exp_text:
                                    st.info(f"💡 {exp_text}")
                            st.markdown("<hr/>", unsafe_allow_html=True)
                
                with t_saq:
                    if not saq_list:
                        st.info(T("No SAQs.", "No SAQs."))
                    else:
                        for idx, q in enumerate(saq_list, 1):
                            (q_id, q_bn, q_en, oa_bn, oa_en, ob_bn, ob_en, oc_bn, oc_en, od_bn, od_en,
                             corr_opt, expl_bn, expl_en, diff, is_desc, m_val, m_ans_bn, m_ans_en, ms_bn, ms_en, qtype) = q
                            q_label = get_q_text(q_bn, q_en)
                            st.markdown(f"""<div class="card-short">
                                <span style="background-color: #059669; color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; float: right;">SAQ</span>
                                <h4>Q{idx}. {q_label}</h4></div>""", unsafe_allow_html=True)
                            with st.expander(T("👁️ View Answer", "👁️ View Answer")):
                                st.markdown(f"**{T('Answer', 'Answer')}:** {corr_opt}")
                                if expl_bn or expl_en:
                                    st.markdown(f"**{T('Explanation', 'Explanation')}:** {get_q_text(expl_bn, expl_en)}")
                            st.markdown("<hr/>", unsafe_allow_html=True)
                
                with t2:
                    if not q2_list:
                        st.info(T("No 2M.", "No 2M."))
                    else:
                        for idx, q in enumerate(q2_list, 1):
                            (q_id, q_bn, q_en, oa_bn, oa_en, ob_bn, ob_en, oc_bn, oc_en, od_bn, od_en,
                             corr_opt, expl_bn, expl_en, diff, is_desc, m_val, m_ans_bn, m_ans_en, ms_bn, ms_en, qtype) = q
                            q_label = get_q_text(q_bn, q_en)
                            st.markdown(f"""<div class="card-broad">
                                <span style="background-color: #7c3aed; color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; float: right;">2 Marks</span>
                                <h4>Q{idx}. {q_label}</h4></div>""", unsafe_allow_html=True)
                            render_ask_button(q_id, idx)
                            st.markdown("<hr/>", unsafe_allow_html=True)
                
                with t3:
                    if not q3_list:
                        st.info(T("No 3M.", "No 3M."))
                    else:
                        for idx, q in enumerate(q3_list, 1):
                            (q_id, q_bn, q_en, oa_bn, oa_en, ob_bn, ob_en, oc_bn, oc_en, od_bn, od_en,
                             corr_opt, expl_bn, expl_en, diff, is_desc, m_val, m_ans_bn, m_ans_en, ms_bn, ms_en, qtype) = q
                            q_label = get_q_text(q_bn, q_en)
                            st.markdown(f"""<div class="card-broad" style="border-left-color: #16a34a;">
                                <span style="background-color: #16a34a; color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; float: right;">3 Marks</span>
                                <h4>Q{idx}. {q_label}</h4></div>""", unsafe_allow_html=True)
                            render_ask_button(q_id, idx)
                            st.markdown("<hr/>", unsafe_allow_html=True)
                
                with t5:
                    if not q5_list:
                        st.info(T("No 5M.", "No 5M."))
                    else:
                        for idx, q in enumerate(q5_list, 1):
                            (q_id, q_bn, q_en, oa_bn, oa_en, ob_bn, ob_en, oc_bn, oc_en, od_bn, od_en,
                             corr_opt, expl_bn, expl_en, diff, is_desc, m_val, m_ans_bn, m_ans_en, ms_bn, ms_en, qtype) = q
                            q_label = get_q_text(q_bn, q_en)
                            st.markdown(f"""<div class="card-broad" style="border-left-color: #dc2626;">
                                <span style="background-color: #dc2626; color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; float: right;">5 Marks</span>
                                <h4>Q{idx}. {q_label}</h4></div>""", unsafe_allow_html=True)
                            render_ask_button(q_id, idx)
                            st.markdown("<hr/>", unsafe_allow_html=True)
        
        elif st_nav == T("❓ My Help / Doubt Requests", "❓ My Help / Doubt Requests"):
            st.subheader(T("❓ My Doubt Requests", "❓ My Doubt Requests"))
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""SELECT d.id, q.question_text, q.question_text_en, q.marks, d.status, d.teacher_answer, d.timestamp
                FROM student_doubts d JOIN questions q ON d.question_id = q.id
                WHERE d.student_username = ? ORDER BY d.id DESC""", (st.session_state.username,))
            my_doubts = cursor.fetchall()
            conn.close()
            if not my_doubts:
                st.info(T("No doubt requests yet.", "No doubt requests yet."))
            else:
                for d_id, q_txt_bn, q_txt_en, q_m, status, t_ans, t_stamp in my_doubts:
                    color = "🟢" if status == "Approved" else "🟡"
                    q_label = get_q_text(q_txt_bn, q_txt_en)
                    with st.expander(f"{color} #{d_id} [{q_m}M] — {status}"):
                        st.markdown(f"**{T('Question', 'Question')}:** {q_label}")
                        if status == "Approved" and t_ans and t_ans.strip():
                            st.success(f"✅ {t_ans}")
                            st.download_button(T("📥 Download", "📥 Download"), data=t_ans, file_name=f"Doubt_{d_id}.txt", key=f"d_{d_id}")
                        else:
                            st.info(f"⏳ Status: {status}")
        
        elif st_nav == T("📄 Mock Tests & Suggestions", "📄 Mock Tests & Suggestions"):
            st.subheader(T("📄 Mock Tests & Suggestions", "📄 Mock Tests & Suggestions"))
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, test_type, code_num, file_name, file_data, uploader, price, timestamp FROM mock_tests WHERE is_published = 1 ORDER BY id DESC")
            mocks = cursor.fetchall()
            conn.close()
            if not mocks:
                st.info(T("No mock tests yet.", "No mock tests yet."))
            else:
                for m_id, t_type, c_num, f_name, f_data, uploader, price, t_stamp in mocks:
                    has_paid = user_has_purchase(st.session_state.username, t_type, m_id)
                    st.markdown(f"### 📄 `{c_num}` — {t_type}")
                    st.caption(f"Uploader: {uploader} | {t_stamp} | ₹{price or 0}")
                    if has_paid:
                        st.success(T("✅ Unlocked!", "✅ Unlocked!"))
                        if f_data:
                            st.download_button(f"📥 {c_num}", data=f_data, file_name=f_name, key=f"dl_{m_id}")
                    else:
                        st.markdown(f"""<div class="lock-box">🔒 {T(f'₹{price or 0} payment unlock করুন।', f'Pay ₹{price or 0} to unlock.')}</div>""", unsafe_allow_html=True)
                    st.markdown("---")
        
        elif st_nav == T("📝 My Exam Submissions", "📝 My Exam Submissions"):
            st.subheader(T("📝 My Exam Submissions", "📝 My Exam Submissions"))
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, test_type, code_num FROM mock_tests WHERE is_published = 1 ORDER BY id DESC")
            my_tests = cursor.fetchall()
            conn.close()
            
            unlocked = [(m[0], m[1], m[2]) for m in my_tests if user_has_purchase(st.session_state.username, m[1], m[0])]
            
            if not unlocked:
                st.warning(T("First unlock a Mock Test.", "First unlock a Mock Test."))
            else:
                test_opts = {f"[{t[1]}] {t[2]}": t[0] for t in unlocked}
                sel_test = st.selectbox(T("Select exam:", "Select exam:"), list(test_opts.keys()), key="sub_exam_sel")
                sub_file = st.file_uploader(T("Answer Sheet Upload", "Answer Sheet Upload"), type=["pdf", "jpg", "jpeg", "png"], key="sub_answer_file")
                if st.button(T("📤 Submit", "📤 Submit"), use_container_width=True, key="sub_ans_btn"):
                    if sub_file is not None:
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
                        st.success(T("🎉 Submitted!", "🎉 Submitted!"))
            
            st.markdown("---")
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""SELECT id, exam_code, submitted_at, status, corrected_file_name, corrected_file_data, corrected_at, admin_note
                FROM exam_submissions WHERE student_username = ? ORDER BY id DESC""", (st.session_state.username,))
            my_submissions = cursor.fetchall()
            conn.close()
            for s_id, ecode, sub_at, stat, cfname, cfdata, cat, note in my_submissions:
                color = "🟢" if stat == "Checked & Returned" else "🟡"
                with st.expander(f"{color} #{s_id} — {ecode} — {stat}"):
                    st.markdown(f"**{T('Submitted', 'Submitted')}:** {sub_at}")
                    if note:
                        st.info(f"{T('Note', 'Note')}: {note}")
                    if stat == "Checked & Returned" and cfdata:
                        st.download_button(T("📥 Download Corrected Copy", "📥 Download Corrected Copy"), data=cfdata, file_name=cfname, key=f"dl_corr_{s_id}")
    
    # ========================================================================
    # TEACHER PORTAL
    # ========================================================================
    elif active_view_role == "teacher":
        if st_nav == T("📥 Assigned Student Doubts", "📥 Assigned Student Doubts"):
            st.subheader(T("📥 Doubts Assigned to You", "📥 Doubts Assigned to You"))
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""SELECT d.id, d.student_name, q.question_text, q.question_text_en, q.marks, d.status, d.teacher_answer
                FROM student_doubts d JOIN questions q ON d.question_id = q.id
                WHERE d.assigned_teacher_username = ? ORDER BY d.id DESC""", (st.session_state.username,))
            my_doubts = cursor.fetchall()
            conn.close()
            if not my_doubts:
                st.info(T("No doubts assigned.", "No doubts assigned."))
            else:
                for d_id, s_name, q_txt_bn, q_txt_en, q_m, status, t_ans in my_doubts:
                    st.markdown(f"""<div class="assigned-card">
                        <strong>📌 #{d_id} [{q_m}M] — {s_name}</strong><br/>
                        <small>Status: {status}</small>
                    </div>""", unsafe_allow_html=True)
                    st.markdown(f"**Q:** {get_q_text(q_txt_bn, q_txt_en)}")
                    if status == "Teacher Submitted (Pending Admin Approval)":
                        st.success(T("✅ Submitted!", "✅ Submitted!"))
                    else:
                        sol_in = st.text_area(T("Solution:", "Solution:"), value=t_ans, key=f"t_sol_{d_id}", height=180)
                        if st.button(T("📤 Submit to Admin", "📤 Submit to Admin"), key=f"t_btn_{d_id}", use_container_width=True):
                            if sol_in.strip():
                                conn = get_connection()
                                cursor = conn.cursor()
                                cursor.execute("""UPDATE student_doubts SET teacher_answer = ?, status = 'Teacher Submitted (Pending Admin Approval)' WHERE id = ?""",
                                               (sol_in.strip(), d_id))
                                conn.commit()
                                conn.close()
                                st.success(T("🎉 Sent!", "🎉 Sent!"))
                                st.rerun()
                    st.markdown("---")
        
        elif st_nav == T("📖 Question Bank Manager", "📖 Question Bank Manager"):
            st.subheader(T("📖 Question Bank Manager", "📖 Question Bank Manager"))
            topic_dict = {t[1]: t[0] for t in cached_topics()}
            if not topic_dict:
                st.error("No chapters.")
                st.stop()
            
            sel_topic_name = st.selectbox(T("Chapter:", "Chapter:"), list(topic_dict.keys()), key="tch_top")
            target_t_id = topic_dict[sel_topic_name]
            
            tab_man, tab_dups, tab_del = st.tabs([
                T("➕ Manual Upload", "➕ Manual Upload"),
                T("🔍 Duplicate Remover", "🔍 Duplicate Remover"),
                T("📖 Browse & Delete", "📖 Browse & Delete")
            ])
            
            with tab_man:
                st.markdown(T("### ➕ Manual Upload", "### ➕ Manual Upload"))
                q_text_bn = st.text_area(T("Question (Bengali):", "Question (Bengali):"), key="tch_q_bn")
                q_en_manual = st.text_input(T("English Translation (Optional):", "English Translation (Optional):"), key="tch_q_en")
                q_type_choice = st.selectbox(T("Type:", "Type:"), [
                    "MCQ (1 Mark)", "SAQ (1 Mark)", "2 Marks", "3 Marks", "5 Marks"
                ], key="tch_q_type_sel")
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
                    co = st.selectbox(T("Correct:", "Correct:"), ["A", "B", "C", "D"], key="tch_co")
                    ex = st.text_area(T("Explanation:", "Explanation:"), key="tch_ex")
                    if st.button(T("Save MCQ", "Save MCQ"), key="tch_save_mcq", use_container_width=True):
                        if q_text_bn and oa:
                            conn = get_connection(); cursor = conn.cursor()
                            cursor.execute("""INSERT INTO questions (topic_id, question_text, question_text_en, option_a, option_b, option_c, option_d, correct_option, explanation, difficulty, is_descriptive, marks, q_type)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Medium', 0, 1, 'MCQ')""",
                                (target_t_id, q_text_bn, q_en_final, oa, ob, oc, od, co, ex))
                            conn.commit(); conn.close()
                            st.cache_data.clear()
                            st.success("✅ Added!"); st.rerun()
                elif is_saq:
                    saq_ans = st.text_area(T("Answer:", "Answer:"), key="tch_saq_ans")
                    saq_ex = st.text_area(T("Explanation:", "Explanation:"), key="tch_saq_ex")
                    if st.button(T("Save SAQ", "Save SAQ"), key="tch_save_saq", use_container_width=True):
                        if q_text_bn and saq_ans:
                            conn = get_connection(); cursor = conn.cursor()
                            cursor.execute("""INSERT INTO questions (topic_id, question_text, question_text_en, correct_option, explanation, difficulty, is_descriptive, marks, q_type)
                                VALUES (?, ?, ?, ?, ?, 'Medium', 0, 1, 'SAQ')""",
                                (target_t_id, q_text_bn, q_en_final, saq_ans, saq_ex))
                            conn.commit(); conn.close()
                            st.cache_data.clear()
                            st.success("✅ Added!"); st.rerun()
                else:
                    ma = st.text_area(T(f"Model Answer ({q_marks}M):", f"Model Answer ({q_marks}M):"), key="tch_ma")
                    ms = st.text_area(T("Marking Scheme:", "Marking Scheme:"), key="tch_ms")
                    if st.button(T(f"Save {q_marks}M", f"Save {q_marks}M"), key="tch_save_broad", use_container_width=True):
                        if q_text_bn:
                            conn = get_connection(); cursor = conn.cursor()
                            cursor.execute("""INSERT INTO questions (topic_id, question_text, question_text_en, difficulty, is_descriptive, marks, model_answer, marking_scheme, q_type)
                                VALUES (?, ?, ?, 'Hard', 1, ?, ?, ?, 'Broad')""",
                                (target_t_id, q_text_bn, q_en_final, q_marks, ma, ms))
                            conn.commit(); conn.close()
                            st.cache_data.clear()
                            st.success("✅ Added!"); st.rerun()
            
            with tab_dups:
                st.markdown(T("### 🔍 Duplicate Remover", "### 🔍 Duplicate Remover"))
                if st.button(T("🔍 Scan", "🔍 Scan"), key="tch_scan"):
                    conn = get_connection(); cursor = conn.cursor()
                    cursor.execute("SELECT id, question_text, marks FROM questions WHERE topic_id = ? ORDER BY id ASC", (target_t_id,))
                    all_q = cursor.fetchall(); conn.close()
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
                            st.success(T("🎉 No duplicates!", "🎉 No duplicates!"))
                        else:
                            st.warning(f"⚠️ {len(groups)} Groups!")
                            for gi, grp in enumerate(groups, 1):
                                keep = st.radio(f"G#{gi}", [q[0] for q in grp],
                                    format_func=lambda x: next(f"#{q[0]} [{q[2]}M]: {q[1][:80]}" for q in grp if q[0] == x),
                                    key=f"k_{gi}_tch")
                                for q in grp:
                                    cA, cB = st.columns([5, 1])
                                    color = "#16a34a" if q[0] == keep else "#dc2626"
                                    cA.markdown(f"<span style='color:{color};font-weight:bold;'>{'✅' if q[0] == keep else '❌'}</span> #{q[0]}")
                                    if q[0] != keep and cB.button(f"🗑️ #{q[0]}", key=f"d_{q[0]}_tch"):
                                        conn = get_connection(); cursor = conn.cursor()
                                        cursor.execute("INSERT INTO duplicate_log (original_q_id, duplicate_q_id, similarity, removed_by) VALUES (?, ?, ?, ?)",
                                                       (keep, q[0], 100.0, st.session_state.full_name))
                                        cursor.execute("DELETE FROM questions WHERE id = ?", (q[0],))
                                        conn.commit(); conn.close()
                                        st.cache_data.clear()
                                        st.rerun()
            
            with tab_del:
                conn = get_connection(); cursor = conn.cursor()
                cursor.execute("SELECT id, question_text, marks FROM questions WHERE topic_id = ? ORDER BY id DESC", (target_t_id,))
                q_rows = cursor.fetchall(); conn.close()
                for q_id, q_txt, q_m in q_rows:
                    c1, c2 = st.columns([5, 1])
                    c1.markdown(f"**#{q_id} [{q_m}M]:** {q_txt[:200]}")
                    if c2.button(f"🗑️", key=f"td_{q_id}"):
                        conn = get_connection(); cursor = conn.cursor()
                        cursor.execute("DELETE FROM questions WHERE id = ?", (q_id,))
                        conn.commit(); conn.close()
                        st.cache_data.clear()
                        st.rerun()
        
        elif st_nav == T("📝 Check Assigned Answer Sheets", "📝 Check Assigned Answer Sheets"):
            st.subheader(T("📝 Check Assigned Answer Sheets", "📝 Check Assigned Answer Sheets"))
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""SELECT id, student_name, exam_code, answer_file_name, answer_file_data, submitted_at, status
                FROM exam_submissions 
                WHERE checker_username = ? AND status IN ('Under Check', 'Teacher Submitted for Admin Review')
                ORDER BY id ASC""", (st.session_state.username,))
            subs = cursor.fetchall()
            conn.close()
            for s_id, s_name, ecode, afname, afdata, sub_at, stat in subs:
                st.markdown(f"""<div class="assigned-card">
                    <strong>📄 #{s_id} — {s_name}</strong><br/>
                    <small>{ecode} | {sub_at} | {stat}</small>
                </div>""", unsafe_allow_html=True)
                if afdata:
                    st.download_button(T("📥 Download Answer Sheet", "📥 Download Answer Sheet"), data=afdata, file_name=afname, key=f"tch_dl_{s_id}")
                if stat == "Under Check":
                    corr_file = st.file_uploader(T("Corrected Copy", "Corrected Copy"), type=["pdf", "jpg", "jpeg", "png"], key=f"tch_corr_{s_id}")
                    tch_note = st.text_area(T("Note:", "Note:"), key=f"tch_note_{s_id}")
                    if st.button(T("📤 Submit to Admin", "📤 Submit to Admin"), key=f"tch_sub_{s_id}", use_container_width=True):
                        if corr_file is not None:
                            cf_bytes = corr_file.getvalue()
                            conn = get_connection(); cursor = conn.cursor()
                            cursor.execute("""UPDATE exam_submissions 
                                SET teacher_corrected_file_name = ?, teacher_corrected_file_data = ?, teacher_note = ?, teacher_submitted_at = CURRENT_TIMESTAMP, status = 'Teacher Submitted for Admin Review'
                                WHERE id = ?""",
                                (corr_file.name, cf_bytes, tch_note.strip(), s_id))
                            conn.commit(); conn.close()
                            st.success(T("🎉 Sent!", "🎉 Sent!"))
                            st.rerun()
                else:
                    st.success(T("✅ Submitted!", "✅ Submitted!"))
                st.markdown("---")
        
        elif st_nav == T("📤 Send Suggestions to Admin", "📤 Send Suggestions to Admin"):
            st.subheader(T("📤 Send Suggestions to Admin", "📤 Send Suggestions to Admin"))
            with st.form("teacher_submit_form"):
                sub_type = st.selectbox(T("Type:", "Type:"), ["Chapter Wise Mock Test", "Final Mock Test", "Board Suggestions"], key="ts_type")
                sub_title = st.text_input(T("Title:", "Title:"), key="ts_title")
                sub_desc = st.text_area(T("Details:", "Details:"), height=120, key="ts_desc")
                sub_price_sug = st.number_input(T("Suggested Price (₹):", "Suggested Price (₹):"), min_value=0, value=0, step=1, key="ts_price")
                sub_file = st.file_uploader(T("Upload File", "Upload File"), type=["pdf", "docx"], key="ts_file")
                if st.form_submit_button(T("📤 Send to Admin", "📤 Send to Admin"), use_container_width=True):
                    if sub_file is not None and sub_title.strip():
                        f_bytes = sub_file.getvalue()
                        conn = get_connection(); cursor = conn.cursor()
                        cursor.execute("""INSERT INTO teacher_submissions (teacher_username, teacher_name, sub_type, title, description, file_name, file_data, status)
                            VALUES (?, ?, ?, ?, ?, ?, ?, 'Pending Admin Review')""",
                            (st.session_state.username, st.session_state.full_name, sub_type,
                             sub_title.strip(), sub_desc.strip() + f"\n[Suggested Price: ₹{sub_price_sug}]",
                             sub_file.name, f_bytes))
                        conn.commit(); conn.close()
                        st.success(T("🎉 Sent!", "🎉 Sent!"))
                        st.balloons()
            
            st.markdown("---")
            st.markdown(f"### 📬 {T('Your Submissions', 'Your Submissions')}")
            conn = get_connection(); cursor = conn.cursor()
            cursor.execute("""SELECT id, sub_type, title, status, admin_note, timestamp FROM teacher_submissions WHERE teacher_username = ? ORDER BY id DESC""", (st.session_state.username,))
            my_subs = cursor.fetchall()
            conn.close()
            for t_id, stype, title, stat, note, ts in my_subs:
                with st.expander(f"#{t_id} — {stype} — {title} [{stat}]"):
                    if note:
                        st.info(f"{T('Admin Note', 'Admin Note')}: {note}")
        
        elif st_nav == T("👨‍🏫 Student Track Records", "👨‍🏫 Student Track Records"):
            st.subheader(T("👨‍🏫 Student Track Records", "👨‍🏫 Student Track Records"))
            conn = get_connection(); cursor = conn.cursor()
            cursor.execute("""SELECT student_name, student_phone, school_name, district, exam_name, topic_name, score, total_questions, percentage, timestamp FROM student_scores ORDER BY timestamp DESC""")
            scores = cursor.fetchall(); conn.close()
            if not scores:
                st.info(T("No records.", "No records."))
            else:
                df = pd.DataFrame(scores, columns=["Name", "Phone", "School", "District", "Exam", "Topic", "Score", "Total", "Pct", "Timestamp"])
                st.dataframe(df, use_container_width=True)
    
    # ========================================================================
    # ADMIN PORTAL
    # ========================================================================
    elif active_view_role == "admin":
        if st_nav == T("🛡️ User Approvals", "🛡️ User Approvals"):
            st.subheader(T("🛡️ User Approvals", "🛡️ User Approvals"))
            conn = get_connection(); cursor = conn.cursor()
            cursor.execute("""SELECT id, role, full_name, school_name, class_grade, phone, district, approved FROM users WHERE is_admin = 0 ORDER BY approved ASC, id DESC""")
            all_u = cursor.fetchall(); conn.close()
            if not all_u:
                st.info("No users.")
            else:
                df_u = pd.DataFrame(all_u, columns=["ID", "Role", "Name", "School", "Class", "Phone", "District", "Approved"])
                st.dataframe(df_u, use_container_width=True)
                sel_uid = st.number_input(T("User ID:", "User ID:"), min_value=1, step=1, key="adm_uid")
                c1, c2 = st.columns(2)
                if c1.button(T("✅ Approve", "✅ Approve"), use_container_width=True, key="adm_approve_btn"):
                    conn = get_connection(); cursor = conn.cursor()
                    cursor.execute("UPDATE users SET approved = 1 WHERE id = ?", (sel_uid,))
                    conn.commit(); conn.close()
                    st.success(f"Approved #{sel_uid}"); st.rerun()
                if c2.button(T("🚫 Revoke", "🚫 Revoke"), use_container_width=True, key="adm_revoke_btn"):
                    conn = get_connection(); cursor = conn.cursor()
                    cursor.execute("UPDATE users SET approved = 0 WHERE id = ?", (sel_uid,))
                    conn.commit(); conn.close()
                    st.rerun()
        
        elif st_nav == T("❓ Student Doubt Assignment Hub", "❓ Student Doubt Assignment Hub"):
            st.subheader(T("❓ Doubt Assignment Hub", "❓ Doubt Assignment Hub"))
            conn = get_connection(); cursor = conn.cursor()
            cursor.execute("""SELECT d.id, d.student_name, q.question_text, q.question_text_en, q.marks, d.assigned_teacher_username, d.teacher_answer, d.status
                FROM student_doubts d JOIN questions q ON d.question_id = q.id 
                ORDER BY CASE WHEN d.status = 'Teacher Submitted (Pending Admin Approval)' THEN 0 WHEN d.status = 'Pending Admin Assignment' THEN 1 ELSE 2 END, d.id DESC""")
            doubts = cursor.fetchall()
            cursor.execute("SELECT username, full_name FROM users WHERE role = 'teacher' AND approved = 1")
            teachers = cursor.fetchall()
            teacher_map = {f"{t[1]} ({t[0]})": t[0] for t in teachers}
            conn.close()
            
            if not doubts:
                st.info("No doubts.")
            else:
                sel_d_id = st.number_input(T("Doubt ID:", "Doubt ID:"), min_value=1, step=1, key="adm_did")
                conn = get_connection(); cursor = conn.cursor()
                cursor.execute("""SELECT d.id, d.student_name, q.question_text, q.question_text_en, q.marks, d.assigned_teacher_username, d.teacher_answer, d.status
                    FROM student_doubts d JOIN questions q ON d.question_id = q.id WHERE d.id = ?""", (sel_d_id,))
                row = cursor.fetchone()
                conn.close()
                if row:
                    d_id, s_name, q_txt_bn, q_txt_en, q_m, t_user, t_ans, d_stat = row
                    st.markdown(f"### #{d_id} [{q_m}M] — {s_name}")
                    st.markdown(f"**Status:** `{d_stat}`")
                    st.markdown(f"**Q:** {get_q_text(q_txt_bn, q_txt_en)}")
                    
                    if t_ans and t_ans.strip() and d_stat == "Teacher Submitted (Pending Admin Approval)":
                        rev_ans = st.text_area(T("Review:", "Review:"), value=t_ans, height=180, key=f"rev_{d_id}")
                        colA, colB = st.columns(2)
                        if colA.button(T("✅ Approve & Unlock", "✅ Approve & Unlock"), key=f"appr_{d_id}", use_container_width=True):
                            conn = get_connection(); cursor = conn.cursor()
                            cursor.execute("UPDATE student_doubts SET teacher_answer = ?, status = 'Approved' WHERE id = ?",
                                           (rev_ans.strip(), d_id))
                            conn.commit(); conn.close()
                            st.rerun()
                        if colB.button(T("🔄 Send Back", "🔄 Send Back"), key=f"back_{d_id}", use_container_width=True):
                            conn = get_connection(); cursor = conn.cursor()
                            cursor.execute("UPDATE student_doubts SET status = 'Assigned to Teacher', teacher_answer = '' WHERE id = ?", (d_id,))
                            conn.commit(); conn.close()
                            st.rerun()
                    elif d_stat == "Pending Admin Assignment":
                        colA, colB = st.columns(2)
                        with colA:
                            if teacher_map:
                                sel_t_lbl = st.selectbox(T("Teacher:", "Teacher:"), list(teacher_map.keys()), key=f"as_{d_id}")
                                if st.button(T("Assign", "Assign"), key=f"asb_{d_id}", use_container_width=True):
                                    conn = get_connection(); cursor = conn.cursor()
                                    cursor.execute("UPDATE student_doubts SET assigned_teacher_username = ?, status = 'Assigned to Teacher' WHERE id = ?",
                                                   (teacher_map[sel_t_lbl], d_id))
                                    conn.commit(); conn.close()
                                    st.rerun()
                        with colB:
                            direct_ans = st.text_area(T("Direct Solution:", "Direct Solution:"), key=f"dir_{d_id}")
                            if st.button(T("Solve & Approve", "Solve & Approve"), key=f"adap_{d_id}", use_container_width=True):
                                if direct_ans.strip():
                                    conn = get_connection(); cursor = conn.cursor()
                                    cursor.execute("UPDATE student_doubts SET teacher_answer = ?, status = 'Approved' WHERE id = ?",
                                                   (direct_ans.strip(), d_id))
                                    conn.commit(); conn.close()
                                    st.rerun()
        
        elif st_nav == T("📖 Question Bank Manager", "📖 Question Bank Manager"):
            st.subheader(T("📖 Question Bank Manager", "📖 Question Bank Manager"))
            topic_dict = {t[1]: t[0] for t in cached_topics()}
            if not topic_dict:
                st.error("No chapters.")
                st.stop()
            
            sel_topic_name = st.selectbox(T("Chapter:", "Chapter:"), list(topic_dict.keys()), key="adm_top")
            target_t_id = topic_dict[sel_topic_name]
            
            tab_ext, tab_man, tab_dups, tab_del = st.tabs([
                T("⚡ PDF/URL Extractor", "⚡ PDF/URL Extractor"),
                T("➕ Manual Upload", "➕ Manual Upload"),
                T("🔍 Duplicate Remover", "🔍 Duplicate Remover"),
                T("📖 Browse & Delete", "📖 Browse & Delete")
            ])
            
            with tab_ext:
                st.markdown(T("### 📤 Auto-Extract Engine", "### 📤 Auto-Extract Engine"))
                source_type = st.radio(T("Source:", "Source:"), [
                    T("📄 Manual Text Paste", "📄 Manual Text Paste"),
                    T("📁 PDF / DOCX", "📁 PDF / DOCX"),
                    T("🌐 URL", "🌐 URL")
                ], key="adm_src")
                extracted_text = ""
                
                if "Manual" in source_type or "ম্যানুয়াল" in source_type:
                    manual_txt = st.text_area(T("Paste Here:", "Paste Here:"), height=250, key="adm_manual_paste")
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
                    if st.button("🌐 Fetch", key="adm_fetch_url_btn"):
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
                    st.markdown(T("#### 📝 Preview:", "#### 📝 Preview:"))
                    edited = st.text_area(T("Review:", "Review:"), value=extracted_text, height=200, key="adm_edit")
                    
                    if detect_mcq_format(edited):
                        st.success(T("🧠 MCQ detected!", "🧠 MCQ detected!"))
                        mcq_parsed = smart_parse_mcq_text(edited)
                        st.info(f"✅ {len(mcq_parsed)} MCQs parsed!")
                        
                        for idx, q in enumerate(mcq_parsed, 1):
                            with st.expander(f"Q{idx}: {q['question'][:80]}..."):
                                st.markdown(f"**Q:** {q['question']}")
                                st.markdown(f"**A)** {q['options']['A']}")
                                st.markdown(f"**B)** {q['options']['B']}")
                                st.markdown(f"**C)** {q['options']['C']}")
                                st.markdown(f"**D)** {q['options']['D']}")
                                st.success(f"✅ {q['correct']}")
                                if q['explanation']:
                                    st.info(f"📝 {q['explanation']}")
                        
                        if st.button(T(f"🚀 Save {len(mcq_parsed)} MCQs", f"🚀 Save {len(mcq_parsed)} MCQs"), key="adm_save_mcq_bulk", use_container_width=True):
                            conn = get_connection(); cursor = conn.cursor()
                            saved = 0
                            for q in mcq_parsed:
                                cursor.execute("""INSERT INTO questions (topic_id, question_text, question_text_en, option_a, option_b, option_c, option_d, correct_option, explanation, difficulty, is_descriptive, marks, q_type)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Medium', 0, 1, 'MCQ')""",
                                    (target_t_id, q['question'], translate_geo_simple(q['question']),
                                     q['options']['A'], q['options']['B'], q['options']['C'], q['options']['D'],
                                     q['correct'], q['explanation']))
                                saved += 1
                            conn.commit(); conn.close()
                            st.cache_data.clear()
                            st.success(f"🎉 {saved} MCQs saved!")
                            st.rerun()
                    else:
                        parsed = parse_and_categorize_questions(edited)
                        st.success(f"{len(parsed)} questions!")
                        if st.button(T("🚀 Save All", "🚀 Save All"), key="adm_save_all"):
                            conn = get_connection(); cursor = conn.cursor()
                            saved = 0
                            for q in parsed:
                                q_bn = q["question"]
                                q_en = translate_geo_simple(q_bn)
                                cursor.execute("""INSERT INTO questions (topic_id, question_text, question_text_en, option_a, option_b, option_c, option_d, correct_option, explanation, difficulty, is_descriptive, marks, model_answer, marking_scheme, q_type)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Medium', ?, ?, ?, ?, ?)""",
                                    (target_t_id, q_bn, q_en, q["opt_a"], q["opt_b"], q["opt_c"], q["opt_d"],
                                     q["correct"], q["explanation"], q["is_descriptive"], q["marks"],
                                     q_bn if q["is_descriptive"] else "", f"{q['marks']}M Scheme",
                                     'MCQ' if q["marks"] == 1 else 'Broad'))
                                saved += 1
                            conn.commit(); conn.close()
                            st.cache_data.clear()
                            st.success(f"Saved {saved}!")
                            st.rerun()
            
            with tab_man:
                st.markdown(T("### ➕ Manual Upload", "### ➕ Manual Upload"))
                q_text_bn = st.text_area(T("Question (Bengali):", "Question (Bengali):"), key="adm_q_bn")
                q_en_manual = st.text_input(T("English Translation (Optional — auto if empty):", "English Translation (Optional — auto if empty):"), key="adm_q_en")
                q_type_choice = st.selectbox(T("Type:", "Type:"), [
                    "MCQ (1 Mark)", "SAQ (1 Mark)", "2 Marks", "3 Marks", "5 Marks"
                ], key="adm_q_type_sel")
                type_marks_map = {"MCQ (1 Mark)": 1, "SAQ (1 Mark)": 1, "2 Marks": 2, "3 Marks": 3, "5 Marks": 5}
                q_marks = type_marks_map[q_type_choice]
                is_mcq = q_type_choice.startswith("MCQ")
                is_saq = q_type_choice.startswith("SAQ")
                q_en_final = q_en_manual.strip() if q_en_manual.strip() else translate_geo_simple(q_text_bn)
                
                if q_text_bn.strip():
                    match, ratio = check_duplicate_question(q_text_bn, target_t_id)
                    if match:
                        st.warning(f"⚠️ Dup ({ratio*100:.1f}%): #{match[0]}")
                
                if is_mcq:
                    c1, c2 = st.columns(2)
                    oa = c1.text_input("A)", key="adm_oa")
                    ob = c2.text_input("B)", key="adm_ob")
                    oc = c1.text_input("C)", key="adm_oc")
                    od = c2.text_input("D)", key="adm_od")
                    co = st.selectbox(T("Correct:", "Correct:"), ["A", "B", "C", "D"], key="adm_co2")
                    ex = st.text_area(T("Explanation:", "Explanation:"), key="adm_ex2")
                    if st.button(T("💾 Save MCQ", "💾 Save MCQ"), key="adm_save_mcq2", use_container_width=True):
                        if q_text_bn and oa:
                            conn = get_connection(); cursor = conn.cursor()
                            cursor.execute("""INSERT INTO questions (topic_id, question_text, question_text_en, option_a, option_b, option_c, option_d, correct_option, explanation, difficulty, is_descriptive, marks, q_type)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Medium', 0, 1, 'MCQ')""",
                                (target_t_id, q_text_bn, q_en_final, oa, ob, oc, od, co, ex))
                            conn.commit(); conn.close()
                            st.cache_data.clear()
                            st.success("✅"); st.rerun()
                elif is_saq:
                    saq_ans = st.text_area(T("Answer:", "Answer:"), key="adm_saq_ans")
                    saq_ex = st.text_area(T("Explanation:", "Explanation:"), key="adm_saq_ex")
                    if st.button(T("💾 Save SAQ", "💾 Save SAQ"), key="adm_save_saq", use_container_width=True):
                        if q_text_bn and saq_ans:
                            conn = get_connection(); cursor = conn.cursor()
                            cursor.execute("""INSERT INTO questions (topic_id, question_text, question_text_en, correct_option, explanation, difficulty, is_descriptive, marks, q_type)
                                VALUES (?, ?, ?, ?, ?, 'Medium', 0, 1, 'SAQ')""",
                                (target_t_id, q_text_bn, q_en_final, saq_ans, saq_ex))
                            conn.commit(); conn.close()
                            st.cache_data.clear()
                            st.success("✅"); st.rerun()
                else:
                    ma = st.text_area(T(f"Model Answer ({q_marks}M):", f"Model Answer ({q_marks}M):"), key="adm_ma2")
                    ms = st.text_area(T("Marking Scheme:", "Marking Scheme:"), key="adm_ms2")
                    if st.button(T(f"💾 Save {q_marks}M", f"💾 Save {q_marks}M"), key="adm_save_b", use_container_width=True):
                        if q_text_bn:
                            conn = get_connection(); cursor = conn.cursor()
                            cursor.execute("""INSERT INTO questions (topic_id, question_text, question_text_en, difficulty, is_descriptive, marks, model_answer, marking_scheme, q_type)
                                VALUES (?, ?, ?, 'Hard', 1, ?, ?, ?, 'Broad')""",
                                (target_t_id, q_text_bn, q_en_final, q_marks, ma, ms))
                            conn.commit(); conn.close()
                            st.cache_data.clear()
                            st.success("✅"); st.rerun()
            
            with tab_dups:
                st.markdown(T("### 🔍 Duplicate Remover", "### 🔍 Duplicate Remover"))
                if st.button(T("🔍 Scan", "🔍 Scan"), key="adm_scan"):
                    conn = get_connection(); cursor = conn.cursor()
                    cursor.execute("SELECT id, question_text, marks FROM questions WHERE topic_id = ? ORDER BY id ASC", (target_t_id,))
                    all_q = cursor.fetchall(); conn.close()
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
                            st.success(T("🎉 No duplicates!", "🎉 No duplicates!"))
                        else:
                            st.warning(f"⚠️ {len(groups)} Groups!")
                            for gi, grp in enumerate(groups, 1):
                                keep = st.radio(f"G#{gi}", [q[0] for q in grp],
                                    format_func=lambda x: next(f"#{q[0]} [{q[2]}M]: {q[1][:80]}" for q in grp if q[0] == x),
                                    key=f"k_{gi}_adm")
                                for q in grp:
                                    cA, cB = st.columns([5, 1])
                                    color = "#16a34a" if q[0] == keep else "#dc2626"
                                    cA.markdown(f"<span style='color:{color};font-weight:bold;'>{'✅' if q[0] == keep else '❌'}</span> #{q[0]}")
                                    if q[0] != keep and cB.button(f"🗑️ #{q[0]}", key=f"d_{q[0]}_adm"):
                                        conn = get_connection(); cursor = conn.cursor()
                                        cursor.execute("INSERT INTO duplicate_log (original_q_id, duplicate_q_id, similarity, removed_by) VALUES (?, ?, ?, ?)",
                                                       (keep, q[0], 100.0, st.session_state.full_name))
                                        cursor.execute("DELETE FROM questions WHERE id = ?", (q[0],))
                                        conn.commit(); conn.close()
                                        st.cache_data.clear()
                                        st.rerun()
            
            with tab_del:
                conn = get_connection(); cursor = conn.cursor()
                cursor.execute("SELECT id, question_text, marks FROM questions WHERE topic_id = ? ORDER BY id DESC", (target_t_id,))
                q_rows = cursor.fetchall(); conn.close()
                for q_id, q_txt, q_m in q_rows:
                    c1, c2 = st.columns([5, 1])
                    c1.markdown(f"**#{q_id} [{q_m}M]:** {q_txt[:200]}")
                    if c2.button(f"🗑️ #{q_id}", key=f"ad_{q_id}"):
                        conn = get_connection(); cursor = conn.cursor()
                        cursor.execute("DELETE FROM questions WHERE id = ?", (q_id,))
                        conn.commit(); conn.close()
                        st.cache_data.clear()
                        st.rerun()
        
        elif st_nav == T("📄 Upload Mock Tests & Suggestions", "📄 Upload Mock Tests & Suggestions"):
            st.subheader(T("📄 Upload Mock Tests", "📄 Upload Mock Tests"))
            t_type = st.radio(T("Type:", "Type:"), ["Chapter Wise Mock Test", "Final Mock Test", "Board Suggestions"], horizontal=True, key="adm_mt")
            default_price = {"Chapter Wise Mock Test": 19, "Final Mock Test": 49, "Board Suggestions": 69}[t_type]
            price = st.number_input(T("Price (₹)", "Price (₹)"), min_value=0, value=default_price, step=1, key="adm_mp")
            conn = get_connection(); cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM mock_tests WHERE test_type = ?", (t_type,))
            cnt = cursor.fetchone()[0]; conn.close()
            prefix = "chapter mock" if t_type == "Chapter Wise Mock Test" else ("final mock" if t_type == "Final Mock Test" else "suggestion")
            auto_code = f"{prefix} - {cnt + 1:03d}"
            st.info(f"Code: `{auto_code}`")
            up_file = st.file_uploader(T("Upload File", "Upload File"), type=["pdf", "docx"], key="adm_mu")
            if st.button(T("🚀 Publish", "🚀 Publish"), key="adm_mpub"):
                if up_file:
                    f_bytes = up_file.getvalue()
                    conn = get_connection(); cursor = conn.cursor()
                    cursor.execute("""INSERT INTO mock_tests (test_type, code_num, file_name, file_data, uploader, price, is_published)
                        VALUES (?, ?, ?, ?, ?, ?, 1)""",
                        (t_type, auto_code, up_file.name, f_bytes, st.session_state.full_name, price))
                    conn.commit(); conn.close()
                    st.cache_data.clear()
                    st.success(f"Published `{auto_code}`!"); st.rerun()
        
        elif st_nav == T("📤 Teacher Submissions Review", "📤 Teacher Submissions Review"):
            st.subheader(T("📤 Teacher Submissions", "📤 Teacher Submissions"))
            conn = get_connection(); cursor = conn.cursor()
            cursor.execute("""SELECT id, teacher_name, sub_type, title, description, file_name, file_data, status, admin_note, timestamp FROM teacher_submissions ORDER BY CASE WHEN status = 'Pending Admin Review' THEN 0 ELSE 1 END, id DESC""")
            t_subs = cursor.fetchall(); conn.close()
            for t_id, tname, stype, title, desc, fname, fdata, stat, note, ts in t_subs:
                with st.expander(f"#{t_id} — {tname} — {stype} — {title} [{stat}]"):
                    st.markdown(f"**{desc}**")
                    if fdata:
                        st.download_button("📥 Download", data=fdata, file_name=fname, key=f"dl_ts_{t_id}")
                    if stat == "Pending Admin Review":
                        admin_note = st.text_input(T("Note:", "Note:"), key=f"tn_{t_id}")
                        default_price = {"Chapter Wise Mock Test": 19, "Final Mock Test": 49, "Board Suggestions": 69}.get(stype, 19)
                        pub_price = st.number_input(T("Final Price:", "Final Price:"), min_value=0, value=default_price, step=1, key=f"tp_{t_id}")
                        colA, colB = st.columns(2)
                        if colA.button(T("✅ Publish", "✅ Publish"), key=f"ap_{t_id}", use_container_width=True):
                            conn = get_connection(); cursor = conn.cursor()
                            cursor.execute("SELECT COUNT(*) FROM mock_tests WHERE test_type = ?", (stype,))
                            cnt2 = cursor.fetchone()[0]
                            prefix = "chapter mock" if stype == "Chapter Wise Mock Test" else ("final mock" if stype == "Final Mock Test" else "suggestion")
                            auto_code = f"{prefix} - {cnt2 + 1:03d}"
                            cursor.execute("""INSERT INTO mock_tests (test_type, code_num, file_name, file_data, uploader, price, is_published)
                                VALUES (?, ?, ?, ?, ?, ?, 1)""",
                                (stype, auto_code, fname, fdata, f"{tname} (via Teacher)", pub_price))
                            new_mock_id = cursor.lastrowid
                            cursor.execute("UPDATE teacher_submissions SET status = 'Published', admin_note = ?, published_mock_id = ? WHERE id = ?", (admin_note.strip(), new_mock_id, t_id))
                            conn.commit(); conn.close()
                            st.cache_data.clear()
                            st.rerun()
                        if colB.button(T("❌ Reject", "❌ Reject"), key=f"rj_{t_id}", use_container_width=True):
                            conn = get_connection(); cursor = conn.cursor()
                            cursor.execute("UPDATE teacher_submissions SET status = 'Rejected', admin_note = ? WHERE id = ?", (admin_note.strip(), t_id))
                            conn.commit(); conn.close()
                            st.rerun()
        
        elif st_nav == T("💡 Ask Corner Suggestions", "💡 Ask Corner Suggestions"):
            st.subheader(T("💡 Ask Corner Suggestions", "💡 Ask Corner Suggestions"))
            conn = get_connection(); cursor = conn.cursor()
            cursor.execute("SELECT id, submitter_name, submitter_role, category, message, admin_reply, status, timestamp FROM ask_corner ORDER BY id DESC")
            asks = cursor.fetchall(); conn.close()
            for a_id, name, role_s, cat, msg, rep, stat, ts in asks:
                color = "#16a34a" if stat == "Replied" else "#dc2626"
                st.markdown(f"""
                    <div class="ask-corner-card" style="border-left-color:{color};">
                    <span style="background:{color};color:white;padding:3px 8px;border-radius:5px;font-size:12px;font-weight:bold;">{stat}</span>
                    <strong style="margin-left:10px;color:#0f172a !important;">#{a_id} — {cat}</strong><br/>
                    <small style="color:#475569 !important;">👤 {name} ({role_s}) — {ts}</small>
                    </div>""", unsafe_allow_html=True)
                st.markdown(f"**{msg}**")
                reply_text = st.text_area(T(f"Reply #{a_id}:", f"Reply #{a_id}:"), value=rep, key=f"ar_{a_id}", height=100)
                cA, cB = st.columns(2)
                if cA.button(T("📤 Send", "📤 Send"), key=f"sr_{a_id}"):
                    conn = get_connection(); cursor = conn.cursor()
                    cursor.execute("UPDATE ask_corner SET admin_reply = ?, status = 'Replied' WHERE id = ?", (reply_text.strip(), a_id))
                    conn.commit(); conn.close()
                    st.rerun()
                if cB.button(T("🗑️ Delete", "🗑️ Delete"), key=f"da_{a_id}"):
                    conn = get_connection(); cursor = conn.cursor()
                    cursor.execute("DELETE FROM ask_corner WHERE id = ?", (a_id,))
                    conn.commit(); conn.close()
                    st.rerun()
                st.markdown("---")
        
        elif st_nav == T("💳 Payment Verifications", "💳 Payment Verifications"):
            st.subheader(T("💳 Payment Verifications", "💳 Payment Verifications"))
            conn = get_connection(); cursor = conn.cursor()
            cursor.execute("""SELECT id, user_name, user_role, phone, item_type, item_id, amount, upi_ref, status, timestamp, admin_note FROM payments ORDER BY CASE WHEN status='Pending Verification' THEN 0 ELSE 1 END, id DESC""")
            pays = cursor.fetchall(); conn.close()
            for p_id, uname, urole, phone, itype, iid, amt, uref, stat, ts, note in pays:
                color = {"Approved": "🟢", "Pending Verification": "🟡", "Rejected": "🔴"}.get(stat, "⚪")
                with st.expander(f"{color} #{p_id} — {uname} ({urole}) — ₹{amt} [{stat}]"):
                    st.markdown(f"**Phone:** {phone} | **Item:** {itype} (ID: {iid})")
                    st.markdown(f"**UPI Ref:** `{uref}` | **Time:** {ts}")
                    if stat == "Pending Verification":
                        adm_note = st.text_input(T("Note:", "Note:"), key=f"pn_{p_id}")
                        cb1, cb2 = st.columns(2)
                        if cb1.button(T("✅ Approve", "✅ Approve"), key=f"pa_{p_id}", use_container_width=True):
                            conn = get_connection(); cursor = conn.cursor()
                            cursor.execute("UPDATE payments SET status = 'Approved', approved_at = CURRENT_TIMESTAMP, admin_note = ? WHERE id = ?", (adm_note.strip(), p_id))
                            cursor.execute("""INSERT INTO user_purchases (username, item_type, item_id, payment_id, status) VALUES (?, ?, ?, ?, 'Active')""", (uname, itype, str(iid), p_id))
                            conn.commit(); conn.close()
                            st.cache_data.clear()
                            st.success("✅ Approved!")
                            st.rerun()
                        if cb2.button(T("❌ Reject", "❌ Reject"), key=f"pr_{p_id}", use_container_width=True):
                            conn = get_connection(); cursor = conn.cursor()
                            cursor.execute("UPDATE payments SET status = 'Rejected', admin_note = ? WHERE id = ?", (adm_note.strip(), p_id))
                            conn.commit(); conn.close()
                            st.cache_data.clear()
                            st.rerun()
        
        elif st_nav == T("📝 Exam Answer Sheet Checking", "📝 Exam Answer Sheet Checking"):
            st.subheader(T("📝 Exam Answer Sheet Checking", "📝 Exam Answer Sheet Checking"))
            conn = get_connection(); cursor = conn.cursor()
            cursor.execute("""SELECT id, student_username, student_name, exam_code, answer_file_name, answer_file_data, submitted_at, checker_username, status, admin_note, teacher_corrected_file_name, teacher_corrected_file_data, teacher_note FROM exam_submissions ORDER BY id DESC""")
            subs = cursor.fetchall()
            cursor.execute("SELECT username, full_name FROM users WHERE role = 'teacher' AND approved = 1")
            teachers = cursor.fetchall()
            teacher_map = {f"{t[1]} ({t[0]})": t[0] for t in teachers}
            conn.close()
            
            for row in subs:
                (s_id, suname, sname, ecode, afname, afdata, sub_at, checker, stat, note, tcfname, tcfdata, tnote) = row
                with st.expander(f"#{s_id} — {sname} — {ecode} [{stat}]"):
                    if afdata:
                        st.download_button(T("📥 Download", "📥 Download"), data=afdata, file_name=afname, key=f"adm_dl_{s_id}")
                    
                    if stat == "Teacher Submitted for Admin Review" and tcfdata:
                        st.download_button(T("📥 Download Teacher's Copy", "📥 Download Teacher's Copy"), data=tcfdata, file_name=tcfname, key=f"dl_tc_{s_id}")
                        final_note = st.text_input(T("Final Note:", "Final Note:"), value=note, key=f"fn_{s_id}")
                        if st.button(T("✅ Return to Student", "✅ Return to Student"), key=f"appr_ret_{s_id}", use_container_width=True):
                            conn = get_connection(); cursor = conn.cursor()
                            cursor.execute("""UPDATE exam_submissions SET corrected_file_name = ?, corrected_file_data = ?, corrected_at = CURRENT_TIMESTAMP, status = 'Checked & Returned', admin_note = ? WHERE id = ?""",
                                           (tcfname, tcfdata, final_note.strip(), s_id))
                            conn.commit(); conn.close()
                            st.rerun()
                    elif stat == "Submitted":
                        colA, colB = st.columns(2)
                        with colA:
                            if teacher_map:
                                sel_t = st.selectbox(T("Teacher:", "Teacher:"), list(teacher_map.keys()), key=f"chk_{s_id}")
                                if st.button(T("Assign", "Assign"), key=f"asg_{s_id}", use_container_width=True):
                                    conn = get_connection(); cursor = conn.cursor()
                                    cursor.execute("UPDATE exam_submissions SET checker_username = ?, status = 'Under Check' WHERE id = ?",
                                                   (teacher_map[sel_t], s_id))
                                    conn.commit(); conn.close()
                                    st.rerun()
                        with colB:
                            corr_file = st.file_uploader(T("Corrected:", "Corrected:"), type=["pdf", "jpg", "png"], key=f"adm_corr_{s_id}")
                            adm_n = st.text_input(T("Note:", "Note:"), key=f"adm_n_{s_id}")
                            if st.button(T("✅ Return", "✅ Return"), key=f"adm_up_{s_id}", use_container_width=True):
                                if corr_file:
                                    cf_bytes = corr_file.getvalue()
                                    conn = get_connection(); cursor = conn.cursor()
                                    cursor.execute("""UPDATE exam_submissions SET corrected_file_name = ?, corrected_file_data = ?, corrected_at = CURRENT_TIMESTAMP, status = 'Checked & Returned', admin_note = ? WHERE id = ?""",
                                                   (corr_file.name, cf_bytes, adm_n.strip(), s_id))
                                    conn.commit(); conn.close()
                                    st.rerun()
                    elif stat == "Under Check":
                        st.info(f"⏳ Under Check by `{checker}`")
                    elif stat == "Checked & Returned":
                        st.success(T("✅ Returned.", "✅ Returned."))
                    
                    if st.button(f"🗑️ Delete", key=f"ds_{s_id}"):
                        conn = get_connection(); cursor = conn.cursor()
                        cursor.execute("DELETE FROM exam_submissions WHERE id = ?", (s_id,))
                        conn.commit(); conn.close()
                        st.rerun()
        
        elif st_nav == T("📊 Analytics & Track Records", "📊 Analytics & Track Records"):
            st.subheader(T("📊 Analytics", "📊 Analytics"))
            conn = get_connection(); cursor = conn.cursor()
            cursor.execute("SELECT student_name, student_phone, school_name, district, exam_name, topic_name, score, total_questions, percentage, timestamp FROM student_scores ORDER BY timestamp DESC")
            scores = cursor.fetchall(); conn.close()
            if not scores:
                st.info(T("No records.", "No records."))
            else:
                df = pd.DataFrame(scores, columns=["Name", "Phone", "School", "District", "Exam", "Topic", "Score", "Total", "Pct", "Timestamp"])
                st.dataframe(df, use_container_width=True)

# ============================================================================
# FOOTER
# ============================================================================
st.markdown("""
    <div class="footer-block">
        <h3 style="margin-bottom: 5px; color: #38bdf8 !important;">Prepared by - Shawon Kar, Sukannya Chakraborty</h3>
        <p style="margin: 3px 0; font-size: 1.1em; font-weight: 500; color: #f8fafc !important;">M.Sc. in Geography (University Of Calcutta)</p>
        <p style="margin: 3px 0; font-size: 1.0em; color: #94a3b8 !important;">B.Ed. (Baba Saheb Ambedkar Education University)</p>
        <p style="margin: 10px 0 0 0; font-weight: bold; color: #38bdf8 !important; font-size: 1.2em;">📞 Ph No - 7001257277</p>
    </div>
""", unsafe_allow_html=True)
