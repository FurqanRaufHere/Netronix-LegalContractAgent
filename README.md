git clone <repo-url>

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

---

## 🗂️ Project Structure

```
project/
├── app/
│   ├── analyzer/           # Clause analysis, LangGraph workflow
│   ├── llm/                # LLM wrappers (Groq, LangChain)
│   ├── utils/              # Clause splitting, text extraction
│   └── comm/               # Email (Resend)
├── chroma_db/              # Chroma vector DB files
├── data/                   # Example data, test docs
├── logs/                   # LLM/agent traces (JSONL)
├── streamlit_app.py        # Main Streamlit UI
├── requirements.txt
├── .env
└── README.md
```

---

## 🛠️ Key Technologies

- **Streamlit**: UI for contract upload, review, and email
- **LangChain**: LLM calls, prompt management
- **LangGraph**: Agent workflow orchestration
- **ChromaDB**: Vector search for precedents
- **Resend**: Email delivery
- **LangSmith**: Observability/tracing for LLM/agent runs

---

## 🧩 Extending the Platform

- Add new tools/APIs by creating new agent nodes (see `app/analyzer/clause_analysis_graph.py`).
- Integrate with Twilio, weather APIs, IoT, or MCP by adding new functions and wiring them into the LangGraph workflow.
- Use LangSmith dashboard to monitor, debug, and optimize your LLM/agent runs.
- Add more UI pages or dashboards in Streamlit for analytics, admin, or user feedback.

---

## 🧪 Testing

```bash
pytest
```

## Resend testing mode (onboarding)

If you don't have a verified sending domain yet, Resend supports a simple onboarding/testing mode:

- Sender: `onboarding@resend.dev` (must be exactly this address)
- Recipient: the recipient must be the account owner's email (the email you used to sign up for Resend)

To use the onboarding sender in this project, set these env vars in `.env`:

```env
RESEND_API_KEY=your_resend_api_key
RESEND_FROM_EMAIL=onboarding@resend.dev
RESEND_OWNER_EMAIL=you@yourdomain.com   # the email you used to sign up with Resend
```

The app performs an explicit check and will refuse to send if the recipient does not match `RESEND_OWNER_EMAIL` when using the onboarding sender. For production, verify a sending domain in Resend and set `RESEND_FROM_EMAIL` to an address from that domain.

## SMTP fallback (Mailtrap / Gmail SMTP)

This project includes an SMTP fallback that will be used automatically if Resend returns verification/403 errors (useful for demos).

Environment variables for SMTP fallback (set these in `.env`):

```env
SMTP_HOST=smtp.mailtrap.io
SMTP_PORT=465
SMTP_USER=your_smtp_user
SMTP_PASS=your_smtp_password
```

Notes:
- For Mailtrap, use the credentials provided by your Mailtrap inbox.
- For Gmail, create an App Password and use `smtp.gmail.com` and port `465`; set `SMTP_USER` to your Gmail address and `SMTP_PASS` to the app password.
- If SMTP variables are not set and Resend fails due to verification, the app will raise an error and show the failure in the UI.

---

## 🆘 Troubleshooting

- **ModuleNotFoundError**: Make sure all dependencies in `requirements.txt` are installed and your virtual environment is activated.
- **API Key Errors**: Double-check your `.env` file for correct keys and restart the app after changes.
- **ChromaDB Warnings**: If you see migration warnings, update your ChromaDB client as shown in the code.
- **LangSmith Tracing**: Ensure your API key is set and check https://smith.langchain.com for traces.

---

## 👤 Authors

- Your Name (and contributors)

---

## 🙏 Acknowledgements

- [LangChain](https://github.com/langchain-ai/langchain)
- [LangGraph](https://github.com/langchain-ai/langgraph)
- [Streamlit](https://streamlit.io/)
- [ChromaDB](https://www.trychroma.com/)
- [Resend](https://resend.com/)
- [LangSmith](https://smith.langchain.com/)
