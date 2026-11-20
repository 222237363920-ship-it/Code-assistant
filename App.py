
import sqlite3
import requests
import streamlit as st

st.set_page_config(page_title="Code Assistant", page_icon="💻")
st.title("💻 Code Assistant")

# ---------- Database ----------
conn = sqlite3.connect("chat.db", check_same_thread=False)
conn.execute(
    "CREATE TABLE IF NOT EXISTS messages "
    "(id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, content TEXT)"
)

def load_messages():
    rows = conn.execute("SELECT role, content FROM messages ORDER BY id").fetchall()
    return [{"role": r, "content": c} for r, c in rows]

def save_message(role, content):
    conn.execute("INSERT INTO messages (role, content) VALUES (?, ?)", (role, content))
    conn.commit()

# ---------- Sidebar settings ----------
with st.sidebar:
    st.header("Settings")
    api_key = st.secrets.get("OPENROUTER_API_KEY", "") or st.text_input(
        "OpenRouter API Key", type="password"
    )
    model = st.text_input("Model name", "qwen/qwen3-coder:free")
    uploaded = st.file_uploader(
        "Attach a code file",
        type=["py", "js", "html", "css", "txt", "json", "java", "cpp"],
    )
    if st.button("🗑️ Clear chat"):
        conn.execute("DELETE FROM messages")
        conn.commit()
        st.rerun()

# ---------- Show chat history ----------
for m in load_messages():
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# ---------- New message ----------
prompt = st.chat_input("Type your coding request here...")

if prompt:
    if not api_key:
        st.error("Enter your OpenRouter API key in the sidebar.")
        st.stop()

    full_prompt = prompt
    if uploaded:
        code = uploaded.read().decode("utf-8", errors="ignore")
        full_prompt += f"\n\nAttached file ({uploaded.name}):\n```\n{code}\n```"

    save_message("user", full_prompt)
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            resp = None
            try:
                resp = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": model, "messages": load_messages()},
                    timeout=120,
                )
                answer = resp.json()["choices"][0]["message"]["content"]
            except Exception as e:
                answer = f"Error: {e}"
                if resp is not None:
                    answer += f"\n\n{resp.text}"
        st.markdown(answer)
    save_message("assistant", answer)
