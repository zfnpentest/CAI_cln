import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from utils import upload_image, get_ai_response
import datetime
import json

# --- 1. PAGE CONFIG ---
st.set_page_config(page_title="Zebra C.AI", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
    .stApp { background-color: #0b0b0b; color: #e0e0e0; }
    .stChatMessage { border-radius: 15px; margin-bottom: 10px; border: 1px solid #222; }
    [data-testid="stSidebar"] { background-color: #111; border-right: 1px solid #333; }
    .stButton>button { border-radius: 12px; border: 1px solid #444; width: 100%; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. FIREBASE INITIALIZATION (WITH PRE-FLIGHT CHECK) ---
@st.cache_resource
def init_db():
    if not firebase_admin._apps:
        try:
            # Check if secrets exist at all
            if "firebase" not in st.secrets:
                st.error("Missing [firebase] section in Streamlit Secrets!")
                st.stop()

            cred_info = dict(st.secrets["firebase"])
            
            # THE REPAIR LOGIC
            raw_key = cred_info.get("private_key", "")
            fixed_key = raw_key.replace("\\n", "\n").strip()
            
            # Ensure headers are clean
            if "-----BEGIN PRIVATE KEY-----" not in fixed_key:
                fixed_key = "-----BEGIN PRIVATE KEY-----\n" + fixed_key
            if "-----END PRIVATE KEY-----" not in fixed_key:
                fixed_key = fixed_key + "\n-----END PRIVATE KEY-----"
            
            cred_info["private_key"] = fixed_key
            
            # Initialize
            cred = credentials.Certificate(cred_info)
            firebase_admin.initialize_app(cred)
        except Exception as e:
            st.error(f"Failed to Initialize Firebase: {e}")
            st.info("Check your TOML formatting in the Streamlit Settings.")
            return None
    return firestore.client()

db = init_db()

# --- 3. SESSION STATE ---
if "username" not in st.session_state: st.session_state.username = None
if "page" not in st.session_state: st.session_state.page = "login"
if "current_char" not in st.session_state: st.session_state.current_char = None

def get_user_pfp():
    # SAFETY: Don't call DB if it failed to initialize or no user is logged in
    if db is None or not st.session_state.username:
        return None
    try:
        doc = db.collection("users").document(st.session_state.username).get()
        return doc.to_dict().get("pfp") if doc.exists else None
    except:
        return None

# --- 4. NAVIGATION ---

# LOGIN PAGE
if st.session_state.page == "login":
    st.title("Zebra C.AI")
    u_in = st.text_input("Username").strip().upper()
    if st.button("Login"):
        if u_in:
            st.session_state.username = u_in
            st.session_state.page = "lobby"
            st.rerun()

# LOBBY PAGE
elif st.session_state.page == "lobby":
    st.title(f"Lobby | {st.session_state.username}")
    
    with st.sidebar:
        pfp = get_user_pfp()
        if pfp: st.image(pfp, width=150)
        if st.button("Logout"):
            st.session_state.username = None
            st.session_state.page = "login"
            st.rerun()

    if st.button("➕ Create Persona"):
        st.session_state.page = "creator"
        st.rerun()

    # Character Grid
    if db:
        chars = [d.to_dict() | {"id": d.id} for d in db.collection("characters").stream()]
        for c in chars:
            with st.container():
                col1, col2, col3 = st.columns([1, 4, 1])
                col1.image(c.get("pfp"), width=80)
                col2.markdown(f"**{c['name']}**\n\n{c.get('description', '')[:50]}...")
                if col3.button("Chat", key=c['id']):
                    st.session_state.current_char = c
                    st.session_state.page = "chat"
                    st.rerun()

# CREATOR PAGE
elif st.session_state.page == "creator":
    st.title("Create Persona")
    if st.button("Back"): st.session_state.page = "lobby"; st.rerun()
    
    with st.form("create"):
        name = st.text_input("Name")
        desc = st.text_area("Personality")
        greet = st.text_area("Greeting")
        img = st.file_uploader("Image", type=["jpg", "png"])
        if st.form_submit_button("Create"):
            if name and desc and img:
                url = upload_image(img)
                db.collection("characters").add({
                    "name": name, "description": desc, "intro_text": greet,
                    "pfp": url, "creator": st.session_state.username
                })
                st.session_state.page = "lobby"; st.rerun()

# CHAT PAGE
elif st.session_state.page == "chat":
    char = st.session_state.current_char
    user_pfp = get_user_pfp()
    chat_id = f"{st.session_state.username}_{char['id']}"

    st.subheader(f"Chatting with {char['name']}")
    if st.button("Exit"): st.session_state.page = "lobby"; st.rerun()

    # History
    messages_ref = db.collection("chats").document(chat_id).collection("messages").order_by("timestamp").stream()
    history = [{"role": m.to_dict()["role"], "content": m.to_dict()["content"]} for m in messages_ref]

    for m in history:
        with st.chat_message(m['role'], avatar=char['pfp'] if m['role']=="assistant" else user_pfp):
            st.markdown(m['content'])

    if prompt := st.chat_input():
        with st.chat_message("user", avatar=user_pfp): st.markdown(prompt)
        db.collection("chats").document(chat_id).collection("messages").add({
            "role": "user", "content": prompt, "timestamp": datetime.datetime.now(datetime.timezone.utc)
        })

        with st.chat_message("assistant", avatar=char['pfp']):
            ctx = [{"role": "system", "content": f"You are {char['name']}. {char['description']}"}]
            ctx += history[-10:]
            ctx.append({"role": "user", "content": prompt})
            ans = get_ai_response(ctx)
            st.markdown(ans)
            db.collection("chats").document(chat_id).collection("messages").add({
                "role": "assistant", "content": ans, "timestamp": datetime.datetime.now(datetime.timezone.utc)
            })
