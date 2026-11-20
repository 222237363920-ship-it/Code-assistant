import re
import sqlite3
import requests
import streamlit as st

st.set_page_config(page_title="Code Assistant", page_icon="💻", layout="wide")

# ---------- Models ----------
# Edit this dict to add or change models (display name -> OpenRouter model id).
MODELS = {
    "Qwen3 Coder (free)": "qwen/qwen3-coder:free",
    "DeepSeek Chat (free)": "deepseek/deepseek-chat-v3-0324:free",
}
CUSTOM = "Custom model id..."

DEFAULT_SYSTEM = (
    "You are an expert programming assistant. Give correct, clean, well-structured "
    "code. Always put code inside fenced markdown blocks with the language name, "
    "and keep explanations short."
)

# ---------- Database ----------
conn = sqlite3.connect("chat_v2.db", check_same_thread=False)
conn.executescript(
    """
    CREATE TABLE IF NOT EXISTS chats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT
    );
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        role TEXT,
        content TEXT,
        model TEXT
    );
    """
)

def create_chat(title):
    cur = conn.execute("INSERT INTO chats (title) VALUES (?)", (title,))
    conn.commit()
    return cur.lastrowid

def list_chats():
    return conn.execute("SELECT id, title FROM chats ORDER BY id DESC LIMIT 20").fetchall()

def load_messages(chat_id):
    if chat_id is None:
        return []
    rows = conn.execute(
        "SELECT role, content, model FROM messages WHERE chat_id=? ORDER BY id",
        (chat_id,),
    ).fetchall()
    return [{"role": r, "content": c, "model": m} for r, c, m in rows]

def save_message(chat_id, role, content, model=None):
    conn.execute(
        "INSERT INTO messages (chat_id, role, content, model) VALUES (?, ?, ?, ?)",
        (chat_id, role, content, model),
    )
    conn.commit()

def delete_chat(chat_id):
    conn.execute("DELETE FROM messages WHERE chat_id=?", (chat_id,))
    conn.execute("DELETE FROM chats WHERE id=?", (chat_id,))
    conn.commit()

# ---------- Rendering (code blocks have a built-in copy button) ----------
def render(content):
    parts = re.split(r"```([\w+-]*)\n(.*?)```", content, flags=re.DOTALL)
    for i in range(0, len(parts), 3):
        text = parts[i].strip()
        if text:
            st.markdown(text)
        if i + 2 < len(parts):
            st.code(parts[i + 2].rstrip("\n"), language=parts[i + 1] or None)

# ---------- Session state ----------
if "chat_id" not in st.session_state:
    st.session_state.chat_id = None
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

# ---------- Sidebar ----------
with st.sidebar:
    st.title("💻 Code Assistant")

    api_key = st.secrets.get("OPENROUTER_API_KEY", "") or st.text_input(
        "OpenRouter API Key", type="password"
    )

    st.subheader("Model")
    choice = st.selectbox("Choose a model", list(MODELS.keys()) + [CUSTOM])
    if choice == CUSTOM:
        model_id = st.text_input("Model id", placeholder="company/model-name")
    else:
        model_id = MODELS[choice]
    st.caption(f"`{model_id}`")

    with st.expander("Advanced"):
        temperature = st.slider("Temperature", 0.0, 1.5, 0.3, 0.1)
        system_prompt = st.text_area("System prompt", DEFAULT_SYSTEM, height=140)

    st.subheader("Attach file")
    uploaded = st.file_uploader(
        "Code file",
        type=["py", "js", "ts", "html", "css", "txt", "json", "java", "cpp", "c", "go", "rs", "md"],
        key=f"uploader_{st.session_state.uploader_key}",
        label_visibility="collapsed",
    )

    st.subheader("Chats")
    if st.button("➕ New chat", use_container_width=True):
        st.session_state.chat_id = None
        st.rerun()
    for cid, title in list_chats():
        label = ("🟢 " if cid == st.session_state.chat_id else "") + (title or "Untitled")
        if st.button(label, key=f"chat_{cid}", use_container_width=True):
            st.session_state.chat_id = cid
            st.rerun()

    if st.session_state.chat_id is not None:
        if st.button("🗑️ Delete this chat", use_container_width=True):
            delete_chat(st.session_state.chat_id)
            st.session_state.chat_id = None
            st.rerun()

# ---------- Main area ----------
st.header("Code Assistant")
st.caption("Ask for code, upload a file to analyze, and copy results with the button on each code block.")

messages = load_messages(st.session_state.chat_id)
if not messages:
    st.info("Start a new conversation below.")

for m in messages:
    with st.chat_message(m["role"]):
        if m["role"] == "assistant" and m["model"]:
            st.caption(f"Model: {m['model']}")
        render(m["content"])

prompt = st.chat_input("Type your coding request here...")

if prompt:
    if not api_key:
        st.error("Enter your OpenRouter API key in the sidebar.")
        st.stop()
    if not model_id:
        st.error("Enter a model id in the sidebar.")
        st.stop()

    full_prompt = prompt
    if uploaded:
        code = uploaded.read().decode("utf-8", errors="ignore")
        full_prompt += f"\n\nAttached file ({uploaded.name}):\n```\n{code}\n```"

    if st.session_state.chat_id is None:
        st.session_state.chat_id = create_chat(prompt[:40])
    chat_id = st.session_state.chat_id

    save_message(chat_id, "user", full_prompt)
    with st.chat_message("user"):
        render(full_prompt)

    history = [{"role": "system", "content": system_prompt}] + [
        {"role": m["role"], "content": m["content"]} for m in load_messages(chat_id)
    ]

    with st.chat_message("assistant"):
        st.caption(f"Model: {model_id}")
        answer, resp = None, None
        with st.spinner("Thinking..."):
            try:
                resp = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model_id,
                        "messages": history,
                        "temperature": temperature,
                    },
                    timeout=180,
                )
                answer = resp.json()["choices"][0]["message"]["content"]
            except Exception as e:
                st.error(f"Request failed: {e}")
                if resp is not None:
                    st.code(resp.text)
        if answer:
            render(answer)

    if answer:
        save_message(chat_id, "assistant", answer, model_id)
        st.session_state.uploader_key += 1
        st.rerun()
