import sys
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

# Project modules (absolute imports)
from app.utils.text_extract import extract_text
from app.analyzer.analyze_document import analyze_document_text
# NOTE: analyze_document_text uses call_groq_chat internally via analyzer


import tempfile
import json
import time
from typing import List, Dict, Any

import streamlit as st

# Defaults from env
DEFAULT_SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
DEFAULT_SMTP_PORT = int(os.getenv("SMTP_PORT", 465))
DEFAULT_SMTP_USER = os.getenv("SMTP_USER", "")
DEFAULT_SMTP_PASS = os.getenv("SMTP_PASS", "")
DEFAULT_MAX_CLAUSES = int(os.getenv("MAX_CLAUSES", 8))  # keep low for demo



# --- email helper (Resend via app.comm.email) ---
from app.comm.email import send_email

# --- UI layout & state bootstrap ---
st.set_page_config(page_title="Contract Risk Analyzer — MVP", layout="wide")
st.title("Contract Risk Analyzer — MVP")

if "uploaded_path" not in st.session_state:
	st.session_state["uploaded_path"] = None
if "extracted_text" not in st.session_state:
	st.session_state["extracted_text"] = ""
if "analysis_results" not in st.session_state:
	st.session_state["analysis_results"] = []  # list of analysis objects
if "selected_for_email" not in st.session_state:
	st.session_state["selected_for_email"] = set()  # clause_id set
if "status" not in st.session_state:
	st.session_state["status"] = ""


# --- Sidebar navigation ---
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Main", "Traces"])

if page == "Main":
    st.sidebar.header("Settings")
    max_clauses = st.sidebar.number_input("Max clauses to analyze (demo)", min_value=1, max_value=50,
                                      value=DEFAULT_MAX_CLAUSES, step=1)
    top_k_precedents = st.sidebar.number_input("Top-k precedents", min_value=0, max_value=10, value=3)
    st.sidebar.markdown("---")
    st.sidebar.header("SMTP (for sending revision email)")
    smtp_host = st.sidebar.text_input("SMTP host", value=DEFAULT_SMTP_HOST)
    smtp_port = st.sidebar.number_input("SMTP port", value=DEFAULT_SMTP_PORT)
    smtp_user = st.sidebar.text_input("SMTP user", value=DEFAULT_SMTP_USER)
    smtp_pass = st.sidebar.text_input("SMTP pass", value=DEFAULT_SMTP_PASS, type="password")
    st.sidebar.markdown("Tip: use SendGrid or Mailtrap for reliable demo inboxes if Gmail blocks you.")


# --- File upload + extraction ---
st.subheader("1) Upload contract (PDF / DOCX / TXT)")
uploaded = st.file_uploader("Upload a contract file", type=["pdf", "docx", "txt"])
if uploaded:
	try:
		tmp = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded.name)[1])
		tmp.write(uploaded.read())
		tmp.flush()
		st.session_state["uploaded_path"] = tmp.name
		st.success(f"Saved upload to {tmp.name}")
	except Exception as e:
		st.error(f"File upload failed: {e}")


# --- Automatic clause analysis after extraction ---
if st.session_state["uploaded_path"]:
	try:
		meta = extract_text(st.session_state["uploaded_path"], return_meta=True)
		text = meta["text"]
		st.session_state["extracted_text"] = text
		if meta.get("is_scanned"):
			st.warning("This PDF looks like a scanned document (low text density). OCR required — results may be empty.")
		st.markdown("### Extracted text (preview)")
		st.code(text[:2000] + ("\n\n... [truncated]" if len(text) > 2000 else ""))

		# Automatically trigger clause analysis if not already done for this upload
		if not st.session_state.get("analysis_results") or st.session_state.get("last_analyzed_path") != st.session_state["uploaded_path"]:
			st.session_state["status"] = "Analyzing clauses..."
			st.info("Extracted text. Now analyzing clauses with LLM agent...")
			with st.spinner("Running clause splitter and LLM analysis (this may take a while)..."):
				try:
					results = analyze_document_text(
						st.session_state["extracted_text"],
						max_clauses=max_clauses,
						top_k_precedents=top_k_precedents
					)
					st.session_state["analysis_results"] = results
					st.session_state["selected_for_email"] = set()
					st.session_state["last_analyzed_path"] = st.session_state["uploaded_path"]
					st.success(f"Analysis complete: {len(results)} clauses processed.")
					st.session_state["status"] = "Analysis complete. Review below."
				except Exception as e:
					st.session_state["analysis_results"] = []
					st.error(f"Analysis failed: {e}")
					st.session_state["status"] = "Analysis failed. See error above."
	except Exception as e:
		st.error(f"Failed to extract text: {e}")
		st.session_state["status"] = "Extraction failed. See error above."

# --- Status display ---
st.subheader("Status")
st.info(st.session_state.get("status", "Idle. Upload a contract to begin."))

# --- Show clause cards if present ---
if st.session_state.get("analysis_results"):
	st.subheader("3) Review clauses and proposed redlines")
	results: List[Dict[str, Any]] = st.session_state["analysis_results"]

	# Pagination control
	per_page = st.number_input("Clauses per page", min_value=1, max_value=20, value=6)
	page = st.number_input("Page", min_value=1, max_value=max(1, (len(results)-1)//per_page + 1), value=1)
	start = (page-1)*per_page
	end = min(len(results), start + per_page)

	for item in results[start:end]:
		cid = item.get("clause_id")
		clause_text = item.get("clause", "")
		analysis = item.get("analysis", {})
		precedents = item.get("precedents", []) or []

		# Card layout
		st.markdown("---")
		st.markdown(f"**Clause {cid}**")
		cols = st.columns([3, 2])
		with cols[0]:
			st.write("Original (truncated):")
			st.text_area(f"clause_{cid}_orig", value=clause_text[:1200], height=140, key=f"clause_orig_{cid}")
		with cols[1]:
			# risk badge
			risk = analysis.get("risk_score", 0)
			risk_color = "red" if risk >=4 else ("orange" if risk>=2 else "green")
			st.markdown(f"**Risk score:** <span style='color:{risk_color}'>{risk}</span>", unsafe_allow_html=True)
			st.write("Reasons:")
			for r in analysis.get("reasons", []):
				st.write("- " + r)
			st.write("Proposed redline (editable):")
			# editable textarea for user to change redline
			default_redline = analysis.get("redline", "")
			user_redline = st.text_area(f"clause_{cid}_redline", value=default_redline, height=120, key=f"redline_{cid}")
			# select checkbox to include in email
			include = st.checkbox("Select this redline for email", value=(cid in st.session_state["selected_for_email"]), key=f"select_{cid}")
			if include:
				st.session_state["selected_for_email"].add(cid)
			else:
				st.session_state["selected_for_email"].discard(cid)

		# Precedents panel
		with st.expander("Top precedents (click to copy)", expanded=False):
			if precedents:
				for i, p in enumerate(precedents):
					st.write(f"Precedent #{i+1}")
					st.text_area(f"precedent_{cid}_{i}", value=p, height=100, key=f"precedent_{cid}_{i}")
			else:
				st.write("No precedents found.")

# --- Email compose and send ---
st.subheader("4) Send selected redlines")
with st.form("send_email_form"):
	to_email = st.text_input("Counterparty email", value="counterparty@example.com")
	subject = st.text_input("Email subject", value="Proposed contract redlines")
	# Build default body from selected clauses
	if st.session_state.get("analysis_results"):
		selected = st.session_state["selected_for_email"]
		if selected:
			body_lines = []
			# map clause_id -> redline value
			id_to_redline = {}
			for k in st.session_state.keys():
				if k.startswith("redline_"):
					# key pattern redline_<cid>
					try:
						_, cid_str = k.split("_", 1)
						id_to_redline[int(cid_str)] = st.session_state[k]
					except Exception:
						pass
			# build body in clause id order
			for item in st.session_state["analysis_results"]:
				cid = item["clause_id"]
				if cid in selected:
					body_lines.append("Original clause:\n" + item["clause"] + "\n")
					body_lines.append("Proposed redline:\n" + id_to_redline.get(cid, item.get("analysis",{}).get("redline","")) + "\n---\n")
			default_body = "\n".join(body_lines)
		else:
			default_body = "Selected no clauses. Use checkboxes to select redlines."
	else:
		default_body = "No analysis results."

	email_body = st.text_area("Email body", value=default_body, height=260)
	submitted = st.form_submit_button("Send email with selected redlines")
	if submitted:
		if not to_email:
			st.error("Provide a counterparty email address.")
		else:
			with st.spinner("Sending email..."):
				try:
					# Use generic send wrapper which will try Resend then SMTP fallback
					from_email = os.getenv("RESEND_FROM_EMAIL")
					api_key = os.getenv("RESEND_API_KEY")
					try:
						resp = send_email(to_email=to_email,
										  subject=subject,
										  body=email_body,
										  resend_api_key=api_key,
										  from_email=from_email)
						used = resp.get("used")
						if used == "resend":
							st.success(f"Email sent via Resend (status {resp.get('status_code')}).")
						elif used == "smtp":
							st.success("Email sent via SMTP fallback.")
							st.warning("Resend failed and SMTP was used as a fallback. Check SMTP settings if this was unexpected.")
						else:
							st.success("Email sent.")
					except Exception as e:
						st.error(f"Email failed: {e}")
				except Exception as e:
					st.error(f"Email failed: {e}")



# --- Traces page ---
if page == "Traces":
    st.header("LLM Analysis Traces")
    st.write("Download logs of all LLM calls (PII redacted). Each line is a JSON object.")
    log_path = "logs/agent_traces.jsonl"
    if os.path.exists(log_path):
        # Redact PII: remove any fields not in allowed set
        allowed_fields = {"ts", "clause_id", "prompt", "response", "risk_score"}
        redacted_lines = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    redacted = {k: v for k, v in obj.items() if k in allowed_fields}
                    redacted_lines.append(json.dumps(redacted, ensure_ascii=False))
                except Exception:
                    continue
        redacted_data = "\n".join(redacted_lines)
        st.download_button("Download redacted traces (JSONL)", data=redacted_data, file_name="agent_traces_redacted.jsonl")
        st.text_area("Preview (first 10 lines)", value="\n".join(redacted_lines[:10]), height=200)
    else:
        st.write("No trace file found yet.")
