import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from utils import upload_image, get_ai_response
import datetime

# --- 1. PAGE SETUP ---
st.set_page_config(page_title="Zebra C.AI", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
    .stApp { background-color: #0b0b0b; color: #e0e0e0; }
    .stChatMessage { white-space: pre-wrap !important; border-radius: 15px; }
    [data-testid="stSidebar"] { background-color: #111; border-right: 1px solid #333; }
    .stButton>button { border-radius: 12px; border: 1px solid #444; transition: 0.3s; }
    .stButton>button:hover { border-color: #ff4b4b; color: #ff4b4b; transform: scale(1.02); }
    </style>
    """, unsafe_allow_html=True)

# --- 2. FIREBASE INIT ---
@st.cache_resource
def init_db():
    if not firebase_admin._apps:
        cred = credentials.Certificate("firebase-key.json")
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_db()

# --- 3. SESSION STATE ---
if "username" not in st.session_state: st.session_state.username = None
if "page" not in st.session_state: st.session_state.page = "login"
if "current_char" not in st.session_state: st.session_state.current_char = None

def get_user_pfp():
    doc = db.collection("users").document(st.session_state.username).get()
    return doc.to_dict().get("pfp") if doc.exists else None

# --- 4. NAVIGATION ---

# LOGIN
if st.session_state.page == "login":
    st.title("Character.AI Clone")
    u_in = st.text_input("Username", placeholder="e.g. ZEBRA").strip().upper()
    if st.button("Enter Lobby"):
        if u_in:
            st.session_state.username = u_in
            st.session_state.page = "lobby"
            st.rerun()

# LOBBY
elif st.session_state.page == "lobby":
    st.title(f"Lobby | {st.session_state.username}")
    
    with st.sidebar:
        st.header("Profile")
        pfp_url = get_user_pfp()
        if pfp_url: st.image(pfp_url, width=120)
        up = st.file_uploader("New Avatar", type=["jpg", "png"])
        if up and st.button("Update PFP"):
            url = upload_image(up)
            db.collection("users").document(st.session_state.username).set({"pfp": url}, merge=True)
            st.rerun()
        st.divider()
        if st.button("Logout"):
            st.session_state.username = None
            st.session_state.page = "login"
            st.rerun()

    chars = [d.to_dict() | {"id": d.id} for d in db.collection("characters").stream()]
    if st.button("➕ Create Persona"):
        st.session_state.page = "creator"
        st.rerun()

    for c in chars:
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([1, 4, 1, 1])
            col1.image(c.get("pfp"), width=80)
            col2.markdown(f"**{c['name']}**\n\n{c.get('description', '')[:100]}...")
            if col3.button("Chat", key=f"chat_{c['id']}"):
                st.session_state.current_char = c
                st.session_state.page = "chat"
                st.rerun()
            if col4.button("🗑️", key=f"del_{c['id']}"):
                db.collection("characters").document(c['id']).delete()
                st.rerun()

# CREATOR
elif st.session_state.page == "creator":
    st.title("New Persona")
    if st.button("← Back"): st.session_state.page = "lobby"; st.rerun()
    with st.form("char_create"):
        name = st.text_input("Name")
        desc = st.text_area("Persona / Bio")
        greet = st.text_area("Greeting Message")
        img = st.file_uploader("Character Image", type=["png", "jpg"])
        if st.form_submit_button("Save"):
            if name and desc and img:
                url = upload_image(img)
                db.collection("characters").add({
                    "name": name, "description": desc, "intro_text": greet,
                    "pfp": url, "creator": st.session_state.username
                })
                st.session_state.page = "lobby"; st.rerun()

# CHAT
elif st.session_state.page == "chat":
    char = st.session_state.current_char
    user_pfp = get_user_pfp()
    chat_id = f"{st.session_state.username}_{char['id']}"

    # Header Row
    h1, h2, h3 = st.columns([1, 4, 1])
    h1.button("← Lobby", on_click=lambda: setattr(st.session_state, 'page', 'lobby'))
    h2.subheader(f"Chatting with {char['name']}")
    
    with h3:
        with st.popover("Character Bio"):
            st.image(char['pfp'], width=100)
            st.markdown(f"**Name:** {char['name']}")
            st.markdown(f"**Bio:**\n{char['description']}")

    # Load History
    messages_ref = db.collection("chats").document(chat_id).collection("messages").order_by("timestamp").stream()
    history = [{"role": m.to_dict()["role"], "content": m.to_dict()["content"]} for m in messages_ref]

    if not history:
        db.collection("chats").document(chat_id).collection("messages").add({
            "role": "assistant", "content": char['intro_text'], "timestamp": datetime.datetime.now(datetime.timezone.utc)
        })
        st.rerun()

    # Display Chat
    for m in history:
        pfp = char['pfp'] if m['role'] == "assistant" else user_pfp
        with st.chat_message(m['role'], avatar=pfp):
            st.markdown(m['content'])

    # Input Logic (Optimized for Speed)
    if prompt := st.chat_input(f"Message {char['name']}..."):
        # Instant UI feedback
        with st.chat_message("user", avatar=user_pfp):
            st.markdown(prompt)
        
        # Background Save
        db.collection("chats").document(chat_id).collection("messages").add({
            "role": "user", "content": prompt, "timestamp": datetime.datetime.now(datetime.timezone.utc)
        })

        # Context & AI Generation
        ctx = [{"role": "system", "content": f"You are {char['name']}. Persona: {char['description']}"}]
        ctx += history[-10:]
        ctx.append({"role": "user", "content": prompt})

        with st.chat_message("assistant", avatar=char['pfp']):
            with st.spinner(f"{char['name']} is typing..."):
                reply = get_ai_response(ctx)
                st.markdown(reply)
                db.collection("chats").document(chat_id).collection("messages").add({
                    "role": "assistant", "content": reply, "timestamp": datetime.datetime.now(datetime.timezone.utc)
                })