"""
Streamlit frontend — AI Document Q&A Platform
Connects to the nginx gateway at http://gateway:80 (inside Docker)
or http://localhost:80 (when running locally).
"""

import os
import time

import requests
import streamlit as st

GATEWAY = os.environ.get("GATEWAY_URL", "http://localhost:80")

# ─── Page config ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="AI Document Q&A",
    page_icon="📄",
    layout="wide",
)

# ─── Session state defaults ───────────────────────────────────────────────────

if "token" not in st.session_state:
    st.session_state.token = None
if "user_email" not in st.session_state:
    st.session_state.user_email = None
if "documents" not in st.session_state:
    st.session_state.documents = []


# ─── Helpers ─────────────────────────────────────────────────────────────────

def auth_headers() -> dict:
    return {"Authorization": f"Bearer {st.session_state.token}"}


def refresh_documents():
    try:
        r = requests.get(f"{GATEWAY}/documents/", headers=auth_headers(), timeout=10)
        if r.status_code == 200:
            st.session_state.documents = r.json()
    except requests.RequestException:
        st.session_state.documents = []


def status_badge(status: str) -> str:
    colors = {
        "uploaded": "🟡",
        "processing": "🔵",
        "ready": "🟢",
        "failed": "🔴",
    }
    return f"{colors.get(status, '⚪')} {status}"


# ─── Auth panel ───────────────────────────────────────────────────────────────

def show_auth():
    st.title("📄 AI Document Q&A")
    st.caption("Upload documents and ask questions — powered by RAG + LLM")

    tab_login, tab_register = st.tabs(["Login", "Register"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", use_container_width=True)

        if submitted:
            try:
                r = requests.post(
                    f"{GATEWAY}/auth/login",
                    json={"email": email, "password": password},
                    timeout=10,
                )
                if r.status_code == 200:
                    st.session_state.token = r.json()["access_token"]
                    st.session_state.user_email = email
                    st.rerun()
                elif r.status_code == 401:
                    st.error("Wrong email or password.")
                else:
                    st.error(f"Error {r.status_code}: {r.text}")
            except requests.RequestException as e:
                st.error(f"Cannot reach gateway: {e}")

    with tab_register:
        with st.form("register_form"):
            reg_email = st.text_input("Email", key="reg_email")
            reg_password = st.text_input("Password", type="password", key="reg_password")
            submitted_reg = st.form_submit_button("Create account", use_container_width=True)

        if submitted_reg:
            try:
                r = requests.post(
                    f"{GATEWAY}/auth/register",
                    json={"email": reg_email, "password": reg_password},
                    timeout=10,
                )
                if r.status_code == 201:
                    st.success("Account created. Please log in.")
                elif r.status_code == 409:
                    st.error("Email already registered.")
                else:
                    st.error(f"Error {r.status_code}: {r.text}")
            except requests.RequestException as e:
                st.error(f"Cannot reach gateway: {e}")


# ─── Main app ─────────────────────────────────────────────────────────────────

def show_app():
    # Sidebar
    with st.sidebar:
        st.markdown(f"**Logged in as**  \n`{st.session_state.user_email}`")
        if st.button("Logout", use_container_width=True):
            st.session_state.token = None
            st.session_state.user_email = None
            st.session_state.documents = []
            st.rerun()

        st.divider()
        st.markdown("### Upload document")

        uploaded_file = st.file_uploader(
            "PDF or TXT, max 50 MB",
            type=["pdf", "txt"],
            label_visibility="collapsed",
        )

        if uploaded_file is not None:
            if st.button("Upload", use_container_width=True):
                with st.spinner("Uploading..."):
                    try:
                        r = requests.post(
                            f"{GATEWAY}/documents/",
                            headers=auth_headers(),
                            files={"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)},
                            timeout=30,
                        )
                        if r.status_code == 202:
                            st.success("Uploaded! Processing started.")
                            refresh_documents()
                        elif r.status_code == 415:
                            st.error("Unsupported format. Use PDF or TXT.")
                        elif r.status_code == 413:
                            st.error("File too large (max 50 MB).")
                        else:
                            st.error(f"Error {r.status_code}: {r.text}")
                    except requests.RequestException as e:
                        st.error(f"Upload failed: {e}")

        st.divider()

        if st.button("Refresh documents", use_container_width=True):
            refresh_documents()

    # ─── Main area ────────────────────────────────────────────────────────────

    st.title("📄 AI Document Q&A")

    refresh_documents()

    if not st.session_state.documents:
        st.info("No documents yet. Upload a PDF or TXT file from the sidebar.")
        return

    # Document list + Q&A
    for doc in st.session_state.documents:
        doc_id = doc["id"]
        filename = doc["filename"]
        status = doc["status"]

        with st.expander(f"{filename}  —  {status_badge(status)}", expanded=False):
            col1, col2 = st.columns([3, 1])

            with col1:
                st.caption(f"ID: `{doc_id}`  |  Created: {doc.get('created_at', '')[:19]}")

            with col2:
                if st.button("Delete", key=f"del_{doc_id}", type="secondary"):
                    try:
                        r = requests.delete(
                            f"{GATEWAY}/documents/{doc_id}",
                            headers=auth_headers(),
                            timeout=10,
                        )
                        if r.status_code == 204:
                            st.success("Deleted.")
                            refresh_documents()
                            st.rerun()
                        else:
                            st.error(f"Error {r.status_code}")
                    except requests.RequestException as e:
                        st.error(str(e))

            if status != "ready":
                if status == "failed":
                    st.error("Processing failed. Try uploading the document again.")
                else:
                    st.warning("Document is still being processed. Refresh to update status.")
            else:
                # Q&A section
                st.markdown("**Ask a question about this document:**")
                question = st.text_input(
                    "Question",
                    key=f"q_{doc_id}",
                    placeholder="What is this document about?",
                    label_visibility="collapsed",
                )

                if st.button("Ask", key=f"ask_{doc_id}", use_container_width=True):
                    if not question.strip():
                        st.warning("Please enter a question.")
                    else:
                        with st.spinner("Thinking..."):
                            t0 = time.time()
                            try:
                                r = requests.post(
                                    f"{GATEWAY}/query/",
                                    headers=auth_headers(),
                                    json={"doc_id": doc_id, "question": question},
                                    timeout=120,
                                )
                                elapsed = time.time() - t0

                                if r.status_code == 200:
                                    data = r.json()
                                    answer = data["answer"]
                                    cached = data.get("cached", False)
                                    chunks = data.get("chunks_used", 0)

                                    st.markdown("**Answer:**")
                                    st.markdown(answer)

                                    meta_cols = st.columns(3)
                                    meta_cols[0].metric("Response time", f"{elapsed:.2f}s")
                                    meta_cols[1].metric("Chunks used", chunks)
                                    meta_cols[2].metric("Source", "Cache" if cached else "LLM")

                                elif r.status_code == 404:
                                    st.error("No relevant content found for this question.")
                                elif r.status_code == 409:
                                    st.warning("Document is not ready yet.")
                                elif r.status_code == 429:
                                    st.error("Rate limit exceeded. Wait a minute and try again.")
                                else:
                                    st.error(f"Error {r.status_code}: {r.text}")
                            except requests.RequestException as e:
                                st.error(f"Request failed: {e}")


# ─── Entry point ──────────────────────────────────────────────────────────────

if st.session_state.token is None:
    show_auth()
else:
    show_app()
