# Contract Risk Analyzer 🚀

[![Streamlit](https://img.shields.io/badge/Streamlit-UI-red?logo=streamlit)](https://streamlit.io/) [![LangChain](https://img.shields.io/badge/LangChain-LLM-blue?logo=python)](https://github.com/langchain-ai/langchain) [![LangGraph](https://img.shields.io/badge/LangGraph-Agents-green)](https://github.com/langchain-ai/langgraph) [![ChromaDB](https://img.shields.io/badge/ChromaDB-VectorDB-purple)](https://www.trychroma.com/) [![LangSmith](https://img.shields.io/badge/LangSmith-Observability-yellow)](https://smith.langchain.com/)

> Modern contract analysis with LLMs, agents, and vector search. Upload contracts, analyze clause risk, and get precedent-based suggestions—all with robust observability and agent workflows.

---

## ✨ Features

- **Streamlit UI**: Upload contracts (PDF/DOCX/TXT), review clause analysis, and send redlines via email.
- **LLM Analysis**: Groq (OpenAI-compatible) via LangChain for clause risk scoring, redline suggestions, and explanations.
- **LangGraph Orchestration**: Clause extraction → LLM analysis → precedent search → logging, all as a graph-based agent workflow.
- **Vector DB Integration**: ChromaDB for precedent search and retrieval.
- **Email Integration**: Resend for sending redline suggestions to counterparties.
- **Observability**: LangSmith tracing for all LLM/agent runs (just add your API key to `.env`).
- **Extensible**: Easily add more tools/APIs (Twilio, weather, IoT, etc).

---


## 🏁 Quickstart

### 1. Clone & Install

```bash
git clone <repo-url>
cd project
python -m venv capstone
./capstone/Scripts/activate
pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file in the project root (see `.env.example`):

```env
GROQ_API_KEY=your_groq_api_key
RESEND_API_KEY=your_resend_api_key
RESEND_FROM_EMAIL=your_verified_sender@example.com
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_api_key
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_PROJECT=default
```

### 3. Run the App

```bash
streamlit run streamlit_app.py
```

Open the local URL in your browser. Upload a contract, analyze, and review results.

# Netronix-LegalContractAgent

This repository contains a Streamlit-based contract analysis assistant that extracts text from uploaded documents, analyzes clauses for risk using a GROQ LLM backend, and can send results by email (Resend primary, SMTP fallback).

This README explains how to run the app locally, configure environment variables, and troubleshoot common deployed-only problems (LLM rate limits, email provider onboarding). It also documents the project structure and testing commands.

**Quick Links**
- **Code:** `streamlit_app.py` (app entry)
- **LLM client:** `app/llm/groq_client.py`
- **Email helpers:** `app/comm/email.py` and `app/comm/templates/`
- **Text extraction:** `app/utils/text_extract.py`
- **Analyzer:** `app/analyzer/analyze_document.py`

**Supported Features**
- **Document extraction:** PDF / DOCX / plain text extraction
- **Clause analysis:** risk scoring, reasons, and redline suggestions via GROQ LLM
- **Email delivery:** Resend API + SMTP fallback (Mailtrap/Gmail app passwords)
- **HTML email templates:** Jinja2 + Premailer in `app/comm/templates`

---

**Prerequisites**
- Python 3.11+ recommended (project uses a venv in `capstone/` for local development).
- Install dependencies:

```powershell
pip install -r requirements.txt
```

---

**Environment (.env)**
Copy `.env.example` to `.env` and fill in real secrets for local development. Key variables used by the app:

- **GROQ / LLM**
	- `GROQ_API_KEY`: your Groq/OpenAI-compatible API key
	- `GROQ_BASE_URL`: (optional) base URL for Groq API
	- `GROQ_MODEL`: model name used for analysis
	- `GROQ_MAX_RETRIES`, `GROQ_RETRY_BASE_DELAY`: retry/backoff tuning for deployed hosts
	- `GROQ_THROTTLE_DELAY_MS`: optional per-request throttle to avoid burst rate limits
	- `DEBUG_LLM_ERRORS`: set `true` in dev to surface extra LLM error info (do NOT enable in public logs)

- **Email (Resend + SMTP fallback)**
	- `EMAIL_BACKEND`: `resend` (default) or `smtp` to force SMTP
	- `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `RESEND_OWNER_EMAIL`
	- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM_EMAIL` (for Mailtrap/Gmail)

- **LangChain (optional)**
	- `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_ENDPOINT`

- **Other**
	- `LOG_DIR`: defaults to `logs`

See `.env.example` for annotated placeholders.

---

**Run locally (development)**

1. Create `.env` from `.env.example` and set keys.
2. Install dependencies: `pip install -r requirements.txt`
3. Launch Streamlit:

```powershell
streamlit run streamlit_app.py
```

Open `http://localhost:8501` in your browser.

Notes:
- If you do not have a verified sending domain in Resend, you will get a 403 when sending from unverified domains (for example `@gmail.com`). Use `RESEND_OWNER_EMAIL` to enable onboarding mode or configure SMTP fallback (Mailtrap) for demos.


