import hashlib
import hmac
import os
import subprocess
import sys
from pathlib import Path

import streamlit as st

from agents.screening_agent import ScreeningAgent
from agents.workflow import AMLWorkflow
from config.roles import PERMISSIONS, scoped_customers
from data.sample_data_generator import generate_sample_data
from database.database import init_db, log_audit, rows
from feedback.feedback_manager import adjusted_finding, submit_feedback
from ingestion.pdf_processor import ingest_regulations
from ingestion.sanctions_loader import load_sanctions
from ingestion.transaction_loader import load_transactions
from rag.vector_store import build_index
from security.authentication import authenticate
from security.rbac import access, customer_in_scope, protect_customer_record


def apply_theme():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
    :root { --ink:#172033; --muted:#6b778a; --line:#e3e8ef; --blue:#2563d9; --blue-soft:#eaf1ff; --canvas:#f3f6fa; --nav:#111827; --nav-line:#29364a; }
    html, body, [class*="css"] { font-family:'DM Sans', sans-serif; color:var(--ink); }
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stAppViewContainer"] > .main, [data-testid="stAppViewContainer"] .main, section[data-testid="stMain"] { background:var(--canvas) !important; }
    [data-testid="stAppViewContainer"] .block-container { background:transparent !important; }
    section[data-testid="stMain"], section[data-testid="stMain"] label, section[data-testid="stMain"] [data-testid="stMarkdownContainer"] { color:var(--ink); }
    section[data-testid="stMain"] input, section[data-testid="stMain"] textarea { color:var(--ink) !important; background:#fff !important; }
    [data-testid="stSidebar"] { background:var(--nav); border-right:1px solid #1e2a3b; }
    [data-testid="stSidebar"] > div:first-child { padding:1.35rem .9rem; }
    [data-testid="stSidebar"] * { color:#dce5f2; }
    [data-testid="stSidebar"] .stRadio label { width:100%; min-height:38px; box-sizing:border-box; display:flex; align-items:center; padding:.62rem .72rem; margin:0; border-radius:7px; font-size:.84rem; border:1px solid transparent; transition:background .15s ease; }
    [data-testid="stSidebar"] .stRadio label > div:first-child,
    [data-testid="stSidebar"] .stRadio input,
    [data-testid="stSidebar"] .stRadio [data-testid="stWidgetLabel"] { display:none !important; }
    [data-testid="stSidebar"] .stRadio [role="radiogroup"] { gap:.18rem; }
    [data-testid="stSidebar"] .stRadio label:hover { background:#1b293c; border-color:#2a3b54; }
    [data-testid="stSidebar"] .stRadio label:has(input:checked) { background:#173b72; border-color:#2e73d7; color:#fff; }
    [data-testid="stSidebar"] .stRadio label:has(input:checked) p { color:#fff; font-weight:600; }
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color:#8ea0b8; }
    [data-testid="stSidebar"] hr { border-color:var(--nav-line); margin:1.2rem 0; }
    [data-testid="stSidebarUserContent"] { padding-bottom:1rem; }
    [data-testid="stSidebar"] .sidebar-user { width:100%; box-sizing:border-box; }
    [data-testid="stSidebar"] .stButton { width:100%; }
    [data-testid="stSidebar"] .stButton button { width:100%; min-height:38px; }
    h1, h2, h3 { font-family:'Space Grotesk', sans-serif; letter-spacing:0; }
    h1 { font-size:2rem; }
    [data-testid="stHeader"], header[data-testid="stHeader"] { background:transparent !important; }
    .brand { display:flex; gap:.7rem; align-items:center; margin-bottom:2.2rem; }
    .brand-mark { display:grid; place-items:center; width:34px; height:34px; border-radius:8px; background:var(--blue); color:white; font-family:'Space Grotesk'; font-weight:700; }
    .brand-name { color:white; font-family:'Space Grotesk'; font-weight:700; font-size:1.05rem; line-height:1.05; }
    .brand-sub { color:#8190a5; font-size:.67rem; margin-top:.2rem; }
    .sidebar-user { background:#172337; border:1px solid #283850; border-radius:9px; padding:.75rem; margin-bottom:1.15rem; }
    .sidebar-user-name { color:#fff; font-size:.86rem; font-weight:600; }
    .sidebar-user-role { color:#93a5bd; font-size:.7rem; margin-top:.18rem; }
    .nav-caption { color:#71839d; font-size:.65rem; font-weight:700; letter-spacing:.12em; text-transform:uppercase; margin:1rem .2rem .4rem; }
    .page-kicker { color:var(--blue); font-size:.68rem; font-weight:700; letter-spacing:.12em; text-transform:uppercase; margin-top:.5rem; }
    .page-head { display:flex; justify-content:space-between; align-items:end; margin-bottom:1.4rem; }
    .page-head h1 { margin:.15rem 0 0; }
    .page-head p { color:var(--muted); margin:0; font-size:.9rem; }
    .status-pill { background:#e6f7ef; color:#13824e; border:1px solid #c8ecd9; border-radius:999px; padding:.38rem .7rem; font-size:.75rem; font-weight:600; }
    div[data-testid="stMetric"] { background:white; border:1px solid var(--line); border-radius:9px; padding:1rem 1.1rem; box-shadow:0 2px 8px rgba(23,34,53,.03); }
    div[data-testid="stMetricLabel"] { color:var(--muted); font-size:.75rem; }
    div[data-testid="stMetricValue"] { color:var(--ink); font-family:'Space Grotesk'; font-size:1.65rem; }
    .section-label { color:var(--muted); font-size:.76rem; font-weight:700; letter-spacing:.05em; text-transform:uppercase; margin:1.6rem 0 .65rem; }
    section[data-testid="stMain"] .section-label { color:#334155 !important; }
    .panel { background:white; border:1px solid var(--line); border-radius:9px; padding:1.1rem; }
    .panel-title { font-family:'Space Grotesk'; font-size:1rem; font-weight:600; margin-bottom:.2rem; }
    .panel-subtitle { color:var(--muted); font-size:.75rem; }
    [data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:9px; overflow:hidden; }
    .stButton > button, [data-testid="stFormSubmitButton"] button { color:var(--ink) !important; background:#fff !important; border:1px solid #cbd5e1 !important; border-radius:7px; font-weight:600; cursor:pointer !important; }
    .stButton > button[kind="primary"], [data-testid="stFormSubmitButton"] button[kind="primary"] { color:#fff !important; background:var(--blue) !important; border-color:var(--blue) !important; }
    [data-testid="stBaseButton-primary"], [data-testid="stFormSubmitButton"] button { color:#fff !important; background:#111827 !important; border-color:#111827 !important; border-radius:7px !important; font-weight:600 !important; }
    [data-testid="stBaseButton-primary"] *, [data-testid="stFormSubmitButton"] button * { color:#fff !important; }
    [data-testid="stBaseButton-primary"]:hover, [data-testid="stFormSubmitButton"] button:hover { background:#24344b !important; border-color:#24344b !important; }
    [data-testid="stSidebar"] .stButton > button { color:#fff !important; background:#1c2b40 !important; border-color:#38506d !important; }
    .assistant-intro { background:#172a46; border-left:4px solid var(--blue); border-radius:10px; padding:1.35rem 1.5rem; color:white; margin:.4rem 0 1rem; }
    .assistant-intro h2 { color:white; margin:0 0 .3rem; font-size:1.35rem; }
    .assistant-intro p { color:#c7dbf7; margin:0; font-size:.84rem; }
    [data-testid="stForm"] { background:#dce8f7; border:1px solid #a9c2df; border-radius:10px; padding:1rem 1.1rem .8rem; box-shadow:0 5px 18px rgba(23,34,53,.07); }
    [data-testid="stTextInput"] input { color:#172033 !important; background:#fff !important; border:1px solid #7892ad !important; border-radius:8px !important; cursor:text !important; caret-color:#2563d9 !important; }
    [data-testid="stTextInput"] input:focus { border-color:#2563d9 !important; box-shadow:0 0 0 2px rgba(37,99,217,.22) !important; }
    [data-testid="stTextInput"] label { color:#172033 !important; font-weight:600; }
    [data-testid="stFileUploader"] section, [data-testid="stFileUploaderDropzone"] { background:#eaf1ff !important; border:1px solid #b7cbe6 !important; border-radius:9px !important; }
    [data-testid="stFileUploader"] label, [data-testid="stFileUploader"] section > div, [data-testid="stFileUploader"] small, [data-testid="stFileUploader"] span { color:#24364d !important; }
    [data-testid="stFileUploader"] button, [data-testid="stFileUploaderDropzone"] button { color:#fff !important; background:#111827 !important; border:1px solid #111827 !important; border-radius:7px !important; }
    [data-testid="stFileUploader"] button *, [data-testid="stFileUploaderDropzone"] button * { color:#fff !important; }
    [data-testid="stFileUploader"] button:hover, [data-testid="stFileUploaderDropzone"] button:hover { background:#24344b !important; border-color:#24344b !important; }
    .answer-panel { background:#fff; border:1px solid var(--line); border-left:4px solid var(--blue); border-radius:9px; padding:1rem 1.15rem; margin-top:1rem; }
    .answer-label { color:var(--blue); font-size:.68rem; font-weight:700; letter-spacing:.1em; text-transform:uppercase; }
    .answer-text { color:var(--ink); font-family:'Space Grotesk'; font-size:1.08rem; line-height:1.45; margin-top:.35rem; }
    .access-badge { display:inline-block; border-radius:999px; padding:.28rem .6rem; font-size:.7rem; font-weight:700; background:#e6f7ef; color:#137d4c; }
    .access-denied { background:#fff0f0; color:#b42318; }
    .workflow-step { border:1px solid var(--line); background:#fff; border-radius:8px; padding:.7rem .8rem; min-height:62px; }
    .workflow-step strong { display:block; color:var(--blue); font-size:.72rem; text-transform:uppercase; letter-spacing:.04em; }
    .workflow-step span { color:var(--ink); font-size:.78rem; }
    .evidence-card { border:1px solid var(--line); border-radius:8px; padding:.8rem; background:#fbfcfe; margin:.45rem 0; }
    .evidence-card strong { color:var(--ink); font-size:.78rem; }
    .evidence-card p { color:#536174; font-size:.78rem; margin:.35rem 0 0; line-height:1.45; }
    .stButton > button, [data-testid="stBaseButton-primary"], [data-testid="stFormSubmitButton"] button, [data-testid="stFileUploader"] button, [data-testid="stFileUploaderDropzone"] button { color:#fff !important; background:#111827 !important; border:1px solid #111827 !important; border-radius:7px !important; font-weight:600 !important; }
    .stButton > button *, [data-testid="stBaseButton-primary"] *, [data-testid="stFormSubmitButton"] button *, [data-testid="stFileUploader"] button *, [data-testid="stFileUploaderDropzone"] button * { color:#fff !important; }
    .stButton > button:hover, [data-testid="stBaseButton-primary"]:hover, [data-testid="stFormSubmitButton"] button:hover, [data-testid="stFileUploader"] button:hover, [data-testid="stFileUploaderDropzone"] button:hover { color:#fff !important; background:#24344b !important; border-color:#24344b !important; }
    .login-shell { max-width:980px; margin:7vh auto 0; background:#fff; border:1px solid var(--line); border-radius:16px; overflow:hidden; box-shadow:0 18px 55px rgba(20,37,54,.12); }
    .login-hero { min-height:420px; margin-top:1.2rem; background:#10283e; border-radius:14px; padding:3rem; color:white; display:flex; flex-direction:column; justify-content:space-between; }
    .login-hero h1 { color:white; font-size:2.35rem; line-height:1.08; margin:.8rem 0 1rem; }
    .login-hero p { color:#bfd1e2; max-width:390px; line-height:1.6; font-size:.9rem; }
    .login-accent { color:#57c3c4; font-size:.7rem; font-weight:700; letter-spacing:.14em; text-transform:uppercase; }
    .login-stat-row { display:flex; gap:2rem; border-top:1px solid #2e465d; padding-top:1.2rem; }
    .login-stat strong { display:block; color:#fff; font-family:'Space Grotesk'; font-size:1.2rem; }
    .login-stat span { color:#91a8bd; font-size:.7rem; }
    .login-card { background:#fff; border:1px solid var(--line); border-radius:14px; padding:2.35rem 2.2rem 1.5rem; margin-top:1.2rem; box-shadow:0 8px 24px rgba(20,37,54,.06); }
    .login-card h2 { margin:0 0 .35rem; font-size:1.45rem; }
    .login-card > p { color:var(--muted); font-size:.82rem; margin:0 0 1.5rem; }
    .demo-note { background:#f0f6fb; border:1px solid #d9e8f3; border-radius:8px; color:#52667a; padding:.75rem; font-size:.72rem; line-height:1.5; margin-top:1rem; }
    @media (max-width: 800px) { .page-head { display:block; } .status-pill { display:inline-block; margin-top:.8rem; } }
    </style>
    """, unsafe_allow_html=True)

def render_brand():
    st.markdown('<div class="brand"><div class="brand-mark">A</div><div><div class="brand-name">AML Guard</div><div class="brand-sub">COMPLIANCE OPERATIONS</div></div></div>', unsafe_allow_html=True)

def get_db():
    connection = init_db(); generate_sample_data()
    if connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0:
        load_transactions(Path("data/transactions.csv"), connection); load_sanctions(Path("data/sanctions.csv"), connection); ingest_regulations(Path("data/regulations")); build_index()
    return connection

def save_upload(uploaded_file):
    upload_dir = Path("data/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / Path(uploaded_file.name).name
    target.write_bytes(uploaded_file.getbuffer())
    return target

def clear_uploaded_data():
    upload_dir = Path("data/uploads")
    if upload_dir.exists():
        for item in upload_dir.iterdir():
            if item.is_file():
                item.unlink()

def session_token(username):
    secret = os.getenv("AML_SESSION_SECRET", "local-demo-session-secret")
    signature = hmac.new(secret.encode(), username.encode(), hashlib.sha256).hexdigest()[:24]
    return f"{username}:{signature}"

def restore_user_from_url():
    token = st.query_params.get("session", "")
    if ":" not in token:
        return None
    username, signature = token.split(":", 1)
    expected = session_token(username).split(":", 1)[1]
    if hmac.compare_digest(signature, expected):
        return authenticate(username, {"admin": "admin123", "analyst": "analyst123", "auditor": "auditor123", "relationship_manager": "rm123"}.get(username, ""))
    return None

def customer_response(question, user, role, connection):
    import re
    customer = re.search(r"C\d{3}", question.upper())
    if not customer: return None
    record = connection.execute("SELECT * FROM transactions WHERE customer_id = ? LIMIT 1", (customer.group(),)).fetchone()
    if not record: return {"answer": "No permitted customer record found."}
    if not customer_in_scope(role, customer.group()):
        log_audit(user, role, "data_retrieval", "customer", "DENIED", connection)
        return {"answer": "ACCESS DENIED", "access_decision": "DENIED"}
    requested_full = any(word in question.lower() for word in ("full", "pii", "private"))
    if requested_full and not access(role, "customer_pii"):
        log_audit(user, role, "data_retrieval", "customer", "DENIED", connection)
        return {"answer": "ACCESS DENIED", "access_decision": "DENIED"}
    permitted, safe = protect_customer_record(role, dict(record))
    log_audit(user, role, "data_retrieval", "customer", "ALLOWED" if permitted else "DENIED", connection)
    return {"answer": "Customer details retrieved." if permitted else "ACCESS DENIED", "customer": safe, "access_decision": "ALLOWED" if permitted else "DENIED"}

def main():
    st.set_page_config(page_title="AML Compliance Assistant", page_icon="A", layout="wide")
    apply_theme()
    connection = get_db()
    if "user" not in st.session_state:
        restored_user = restore_user_from_url()
        if restored_user:
            st.session_state.user = restored_user
    if "user" not in st.session_state:
        left_login, right_login = st.columns([1.08, .92], gap="small")
        with left_login:
            st.markdown('<div class="login-hero"><div><div class="login-accent">AML Guard · Secure workspace</div><h1>Make every transaction explainable.</h1><p>Screen risk, investigate anomalies, and connect every decision to permitted evidence in one controlled compliance platform.</p></div><div class="login-stat-row"><div class="login-stat"><strong>200+</strong><span>Demo transactions</span></div><div class="login-stat"><strong>RBAC</strong><span>Role-aware access</span></div><div class="login-stat"><strong>RAG</strong><span>Evidence retrieval</span></div></div></div>', unsafe_allow_html=True)
        with right_login:
            st.markdown('<div class="login-card"><h2>Welcome back</h2><p>Sign in to your compliance workspace.</p></div>', unsafe_allow_html=True)
            with st.form("login"):
                username = st.text_input("Username", value="analyst")
                password = st.text_input("Password", type="password", value="analyst123")
                if st.form_submit_button("Sign in to AML Guard", type="primary", use_container_width=True):
                    user = authenticate(username, password)
                    if user:
                        st.session_state.user = user
                        st.query_params["session"] = session_token(user["username"])
                        log_audit(user["username"], user["role"], "login", "session", "ALLOWED", connection)
                        st.rerun()
                    else: st.error("Invalid username or password")
            st.markdown('<div class="demo-note"><strong>Demo access</strong><br>admin / admin123 · analyst / analyst123 · auditor / auditor123<br>relationship_manager / rm123<br><span style="font-size:.68rem"></span></div>', unsafe_allow_html=True)
        return
    user = st.session_state.user; role = user["role"]
    with st.sidebar:
        render_brand()
        page = st.radio("Workspace", ["Dashboard", "AML Assistant", "Data Ingestion", "Alerts", "Feedback", "Evaluation", "Audit Logs"], label_visibility="collapsed")
        st.markdown('<div class="nav-caption">Access scope</div>', unsafe_allow_html=True)
        st.caption(" · ".join(permission.replace("_", " ").title() for permission in sorted(PERMISSIONS[role])))
        st.markdown('<hr>', unsafe_allow_html=True)
        st.markdown(f'<div class="sidebar-user"><div class="sidebar-user-name">{user["username"]}</div><div class="sidebar-user-role">{role.replace("_", " ").title()}</div></div>', unsafe_allow_html=True)
        if st.button("Logout"):
            log_audit(user["username"], role, "logout", "session", "ALLOWED", connection)
            st.query_params.clear()
            del st.session_state.user
            st.rerun()
    if page == "Dashboard":
        st.markdown('<div class="page-head"><div><div class="page-kicker">OVERVIEW</div><h1>Compliance overview</h1><p>Monitor risk signals and investigation activity across your permitted dataset.</p></div><div class="status-pill">● System operational</div></div>', unsafe_allow_html=True)
        transactions = connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        findings = ScreeningAgent(connection).run(customer_ids=scoped_customers(role))
        sanctions_count = sum(f["sanctions_match"]["status"] != "No match" for f in findings)
        open_alerts = connection.execute("SELECT COUNT(*) FROM alerts WHERE status='OPEN'").fetchone()[0]
        cards = st.columns(5)
        cards[0].metric("Total transactions", f"{transactions:,}", "Live dataset")
        cards[1].metric("High risk alerts", len(findings), "Needs review")
        cards[2].metric("Sanctions matches", sanctions_count, "Exact or possible")
        cards[3].metric("Open alerts", open_alerts, "Awaiting action")
        cards[4].metric("Evidence chunks", len(__import__("rag.vector_store", fromlist=["load_documents"]).load_documents()), "Indexed regulations")
        st.markdown('<div class="section-label">Activity trends</div>', unsafe_allow_html=True)
        left, right = st.columns(2)
        with left:
            st.markdown('<div class="panel"><div class="panel-title">Alert volume</div><div class="panel-subtitle">Current screening distribution</div></div>', unsafe_allow_html=True)
            st.bar_chart({"High risk": [len([f for f in findings if f["risk_level"] == "HIGH"])], "Medium risk": [len([f for f in findings if f["risk_level"] == "MEDIUM"])], "Sanctions": [sanctions_count]}, height=190)
        with right:
            st.markdown('<div class="panel"><div class="panel-title">Risk signals</div><div class="panel-subtitle">Rule triggers in the current dataset</div></div>', unsafe_allow_html=True)
            reason_counts = {}
            for finding in findings:
                for reason in finding["reasons"]: reason_counts[reason] = reason_counts.get(reason, 0) + 1
            st.bar_chart(reason_counts or {"No signals": 0}, height=190)
        st.markdown('<div class="section-label">Real-time transaction monitoring</div>', unsafe_allow_html=True)
        table = [{"Transaction ID": f["transaction_id"], "Amount": f["amount"], "Country": f["country"], "Risk": f["risk_level"], "Score": f["risk_score"], "Flags": ", ".join(f["reasons"][:2])} for f in findings[:15]]
        st.dataframe(table, use_container_width=True, hide_index=True)
    elif page == "AML Assistant":
        st.markdown('<div class="page-kicker">INVESTIGATION WORKSPACE</div><h1>AML Assistant</h1>', unsafe_allow_html=True)
        st.markdown('<div class="assistant-intro"><h2>Ask a compliance question</h2><p>Search permitted transaction data, sanctions results, and regulatory evidence in one controlled workflow.</p></div>', unsafe_allow_html=True)
        with st.form("assistant_query"):
            question = st.text_input("Natural-language question", value="Show suspicious transactions this month.", label_visibility="visible")
            submitted = st.form_submit_button("Run investigation", type="primary", use_container_width=True)
        if submitted:
            customer = customer_response(question, user["username"], role, connection)
            st.session_state.assistant_result = customer or AMLWorkflow(connection).run(question, user["username"], role)
        result = st.session_state.get("assistant_result")
        if result:
            allowed = result.get("access_decision", "ALLOWED") == "ALLOWED"
            badge_class = "access-badge" if allowed else "access-badge access-denied"
            answer = result.get("answer") or result.get("final_answer")
            st.markdown(f'<div class="answer-panel"><div class="answer-label">Final response</div><div class="answer-text">{answer}</div><div style="margin-top:.7rem"><span class="{badge_class}">{"ACCESS ALLOWED" if allowed else "ACCESS DENIED"}</span></div></div>', unsafe_allow_html=True)
            if result.get("customer"):
                st.markdown('<div class="section-label">Permitted customer view</div>', unsafe_allow_html=True)
                st.json(result["customer"])
            if result.get("workflow"):
                st.markdown('<div class="section-label">Investigation trace</div>', unsafe_allow_html=True)
                steps = st.columns(4)
                labels = [("01", "RBAC check"), ("02", "Screening agent"), ("03", "Investigation agent"), ("04", "Evidence response")]
                for slot, (number, label) in zip(steps, labels):
                    with slot: st.markdown(f'<div class="workflow-step"><strong>{number}</strong><span>{label}</span></div>', unsafe_allow_html=True)
                findings = result.get("verification", [])
                st.markdown('<div class="section-label">Verified findings</div>', unsafe_allow_html=True)
                if findings:
                    st.dataframe([{"Transaction": f["transaction_id"], "Risk": f["final_priority"], "Score": f["risk_score"], "Country": f["country"], "Reasons": ", ".join(f["reasons"][:2])} for f in findings[:20]], use_container_width=True, hide_index=True)
                    for finding in findings[:5]:
                        with st.expander(f"Evidence · {finding['transaction_id']} · {finding['final_priority']}"):
                            st.write(finding["verification"])
                            for evidence in finding["regulatory_evidence"]:
                                st.markdown(f'<div class="evidence-card"><strong>{evidence["document_name"]} · Page {evidence["page_number"]}</strong><p>{evidence["text"]}</p></div>', unsafe_allow_html=True)
    elif page == "Data Ingestion":
        st.markdown('<div class="page-kicker">DATA SOURCES</div><h1>Data ingestion</h1><p>Use the predefined demo set for a quick start, or upload your own bank data and regulatory material.</p>', unsafe_allow_html=True)
        st.markdown('<div class="section-label">Predefined data</div>', unsafe_allow_html=True)
        if st.button("Load predefined demo data", type="primary"):
            clear_uploaded_data(); generate_sample_data(); load_transactions("data/transactions.csv", connection); load_sanctions("data/sanctions.csv", connection); documents = ingest_regulations("data/regulations"); build_index(); st.success(f"Reset to demo data: loaded transactions, sanctions, and {len(documents)} regulatory chunks")
        st.caption("Includes 200 synthetic transactions, a demo sanctions watchlist, and clearly labeled sample regulatory material.")
        st.markdown('<div class="section-label">Add your data</div>', unsafe_allow_html=True)
        transaction_file = st.file_uploader("Transactions CSV or Excel", type=["csv", "xlsx", "xls"], key="transactions_upload")
        sanctions_file = st.file_uploader("Sanctions/watchlist CSV or Excel", type=["csv", "xlsx", "xls"], key="sanctions_upload")
        regulation_files = st.file_uploader("Regulatory PDF documents", type=["pdf"], accept_multiple_files=True, key="regulations_upload")
        if st.button("Ingest uploaded data"):
            try:
                loaded = []
                if transaction_file:
                    loaded.append(f"{load_transactions(save_upload(transaction_file), connection)} transactions")
                if sanctions_file:
                    loaded.append(f"{load_sanctions(save_upload(sanctions_file), connection)} sanctions")
                if regulation_files:
                    for uploaded in regulation_files: save_upload(uploaded)
                    documents = ingest_regulations("data/uploads"); build_index(); loaded.append(f"{len(documents)} regulatory chunks")
                if loaded: st.success("Ingested " + ", ".join(loaded))
                else: st.warning("Choose at least one file before ingesting.")
            except (ValueError, OSError) as error:
                st.error(f"Ingestion failed: {error}")
        st.markdown('<div class="section-label">Current records</div>', unsafe_allow_html=True)
        st.write("Transactions:", connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], "| Sanctions:", connection.execute("SELECT COUNT(*) FROM sanctions").fetchone()[0])
    elif page == "Alerts":
        st.header("Alerts")
        findings = ScreeningAgent(connection).run(customer_ids=scoped_customers(role))
        st.dataframe(findings, use_container_width=True)
    elif page == "Feedback":
        st.header("Analyst feedback")
        findings = ScreeningAgent(connection).run(customer_ids=scoped_customers(role))
        if findings:
            finding = st.selectbox("Finding", findings, format_func=lambda item: item["transaction_id"])
            st.write(f"Before feedback: {finding['risk_score']} / {finding['risk_level']}")
            decision = st.selectbox("Decision", ["TRUE HIT", "FALSE POSITIVE", "ESCALATE"])
            if st.button("Submit feedback"):
                submit_feedback(connection, None, finding["transaction_id"], decision, "Recorded from dashboard", user["username"])
                after = adjusted_finding(finding, connection); st.success(f"After feedback: {after['risk_score']} / {after['risk_level']}")
    elif page == "Evaluation":
        st.header("Evaluation")
        st.write("Use this check to quickly confirm that the main AML Guard features are working with the demo data.")
        st.info("Click **Run evaluation** below. A **PASS** means that feature is working as expected; the final pass rate shows the overall result.")
        if st.button("Run evaluation", type="primary"):
            st.markdown("**Evaluation results**")
            completed = subprocess.run(
                [sys.executable, "evaluation/evaluate.py"],
                capture_output=True,
                text=True,
                cwd=Path(__file__).resolve().parent,
                check=False,
            )
            output = completed.stdout
            if completed.stderr:
                output += f"\n{completed.stderr}"
            st.code(output or "Evaluation finished without output.")
            if completed.returncode:
                st.error(f"Evaluation could not complete (exit code {completed.returncode}). Check the details above.")
    else:
        st.header("Audit logs"); st.dataframe(rows(connection, "SELECT username, role, action, resource, access_decision, timestamp FROM audit_logs ORDER BY id DESC LIMIT 100"), use_container_width=True)

if __name__ == "__main__": main()
