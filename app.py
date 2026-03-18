import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from utils import upload_image, get_ai_response
import datetime
import json

# --- 1. PAGE CONFIG & STYLING ---
st.set_page_config(page_title="Zebra C.AI", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
    .stApp { background-color: #0b0b0b; color: #e0e0e0; }
    .stChatMessage { border-radius: 15px; margin-bottom: 10px; }
    [data-testid="stSidebar"] { background-color: #111; border-right: 1px solid #333; }
    .stButton>button { border-radius: 12px; border: 1px solid #444; transition: 0.2s; width: 100%; }
    .stButton>button:hover { border-color: #ff4b4b; color: #ff4b4b; background-color: #1a1a1a; }
    /* Character Card Styling */
    .char-card { padding: 15px; border: 1px solid #333; border-radius: 15px; background: #161616; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. FIREBASE INITIALIZATION (JWT FIX) ---
@st.cache_resource
def init_db():
    if not firebase_admin._apps:
        try:
            # 1. Pull from Streamlit Secrets
            cred_dict = dict(st.secrets["firebase"])
            
            # 2. Clean the RSA Private Key (Fixes Invalid JWT Signature)
            raw_key = cred_dict["private_key"]
            cred_dict["private_key"] = raw_key.replace("\\n", "\n").strip()
            
            # 3. Initialize with cleaned credentials
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        except Exception as e:
            st.error(f"🔥 Database Connection Error: {e}")
            st.stop()
    return firestore.client()

db = init_db()

# --- 3. SESSION STATE MANAGEMENT ---
if "username" not in st.session_state: st.session_state.username = None
if "page" not in st.session_state: st.session_state.page = "login"
if "current_char" not in st.session_state: st.session_state.current_char = None

def get_user_pfp():
    if not st.session_state.username: return None
    doc = db.collection("users").document(st.session_state.username).get()
    return doc.to_dict().get("pfp") if doc.exists else None

# --- 4. NAVIGATION LOGIC ---

# PAGE: LOGIN
if st.session_state.page == "login":
    st.title("Character.AI Clone")
    st.caption("March 2026 Build | Powered by Gemini Flash Lite")
    u_in = st.text_input("Username", placeholder="e.g. ZEBRA").strip().upper()
    if st.button("Enter Lobby"):
        if u_in:
            st.session_state.username = u_in
            st.session_state.page = "lobby"
            st.rerun()

# PAGE: LOBBY
elif st.session_state.page == "lobby":
    st.title(f"Lobby | Welcome, {st.session_state.username}")
    
    with st.sidebar:
        st.header("My Profile")
        pfp = get_user_pfp()
        if pfp: st.image(pfp, width=150)
        
        up = st.file_uploader("Change Avatar", type=["jpg", "png"])
        if up and st.button("Update Profile Picture"):
            url = upload_image(up)
            db.collection("users").document(st.session_state.username).set({"pfp": url}, merge=True)
            st.success("Avatar Updated!")
            st.rerun()
            
        st.divider()
        if st.button("Logout"):
            st.session_state.username = None
            st.session_state.page = "login"
            st.rerun()

    # Persona Grid
    st.subheader("Your AI Personas")
    if st.button("➕ Create New Persona"):
        st.session_state.page = "creator"
        st.rerun()

    chars = [d.to_dict() | {"id": d.id} for d in db.collection("characters").stream()]
    for c in chars:
        with st.container():
            col1, col2, col3, col4 = st.columns([1, 4, 1, 1])
            with col1: st.image(c.get("pfp"), width=80)
            with col2: st.markdown(f"### {c['name']}\n{c.get('description', '')[:80]}...")
            with col3: 
                if st.button("Chat", key=f"chat_{c['id']}"):
                    st.session_state.current_char = c
                    st.session_state.page = "chat"
                    st.rerun()
            with col4:
                if st.button("🗑️", key=f"del_{c['id']}"):
                    db.collection("characters").document(c['id']).delete()
                    st.rerun()

# PAGE: CREATOR
elif st.session_state.page == "creator":
    st.title("Persona Workshop")
    if st.button("← Cancel"): st.session_state.page = "lobby"; st.rerun()
    
    with st.form("char_create"):
        name = st.text_input("Persona Name")
        desc = st.text_area("Full Bio / System Prompt", help="Define how the AI thinks and acts.")
        greet = st.text_area("Greeting Message", placeholder="Hello! I am...")
        img = st.file_uploader("Profile Image", type=["png", "jpg"])
        
        if st.form_submit_button("Bring to Life"):
            if name and desc and img:
                with st.spinner("Uploading to cloud..."):
                    url = upload_image(img)
                    db.collection("characters").add({
                        "name": name, "description": desc, "intro_text": greet,
                        "pfp": url, "creator": st.session_state.username
                    })
                st.session_state.page = "lobby"; st.rerun()

# PAGE: CHAT
elif st.session_state.page == "chat":
    char = st.session_state.current_char
    user_pfp = get_user_pfp()
    chat_id = f"{st.session_state.username}_{char['id']}"

    # Header with Bio Popover
    h_col1, h_col2, h_col3 = st.columns([1, 4, 1])
    h_col1.button("← Lobby", on_click=lambda: setattr(st.session_state, 'page', 'lobby'))
    h_col2.subheader(f"Conversation: {char['name']}")
    
    with h_col3:
        with st.popover("👤 View Bio"):
            st.image(char['pfp'], width=100)
            st.write(f"**Name:** {char['name']}")
            st.divider()
            st.write(f"**Bio:**\n{char['description']}")

    # Load and Render Chat History
    messages_ref = db.collection("chats").document(chat_id).collection("messages").order_by("timestamp").stream()
    history = [{"role": m.to_dict()["role"], "content": m.to_dict()["content"]} for m in messages_ref]

    # Greeting if Chat is Empty
    if not history:
        db.collection("chats").document(chat_id).collection("messages").add({
            "role": "assistant", "content": char['intro_text'], 
            "timestamp": datetime.datetime.now(datetime.timezone.utc)
        })
        st.rerun()

    for m in history:
        with st.chat_message(m['role'], avatar=char['pfp'] if m['role'] == "assistant" else user_pfp):
            st.markdown(m['content'])

    # Optimistic Chat Input
    if prompt := st.chat_input(f"Message {char['name']}..."):
        # 1. Display User Message Instantly
        with st.chat_message("user", avatar=user_pfp):
            st.markdown(prompt)
        
        # 2. Save User Message to DB
        db.collection("chats").document(chat_id).collection("messages").add({
            "role": "user", "content": prompt, "timestamp": datetime.datetime.now(datetime.timezone.utc)
        })

        # 3. AI Processing
        with st.chat_message("assistant", avatar=char['pfp']):
            with st.spinner(f"{char['name']} is typing..."):
                ctx = [{"role": "system", "content": f"You are {char['name']}. Persona: {char['description']}"}]
                ctx += history[-15:] # Long memory
                ctx.append({"role": "user", "content": prompt})
                
                reply = get_ai_response(ctx)
                st.markdown(reply)
                
                # 4. Save AI Reply to DB
                db.collection("chats").document(chat_id).collection("messages").add({
                    "role": "assistant", "content": reply, 
                    "timestamp": datetime.datetime.now(datetime.timezone.utc)
                })
