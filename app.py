import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from utils import upload_image, get_ai_response
import datetime
import json
import os

# --- 1. PAGE CONFIG & STYLING ---
st.set_page_config(page_title="Zebra C.AI", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
    .stApp { background-color: #0b0b0b; color: #e0e0e0; }
    .stChatMessage { border-radius: 15px; margin-bottom: 10px; border: 1px solid #222; }
    [data-testid="stSidebar"] { background-color: #111; border-right: 1px solid #333; }
    .stButton>button { border-radius: 12px; border: 1px solid #444; transition: 0.2s; width: 100%; }
    .stButton>button:hover { border-color: #ff4b4b; color: #ff4b4b; background-color: #1a1a1a; }
    /* Mobile-friendly adjustments */
    @media (max-width: 600px) {
        .stImage { width: 100% !important; }
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. FIREBASE INITIALIZATION (ULTIMATE JWT FIX) ---
@st.cache_resource
def init_db():
    if not firebase_admin._apps:
        try:
            # Load secret as a standard dictionary
            cred_info = dict(st.secrets["firebase"])
            
            # THE FIX: Force correct RSA newline formatting
            # This handles literal \n, double-escaped \\n, and actual line breaks
            raw_key = cred_info["private_key"]
            fixed_key = raw_key.replace("\\n", "\n").strip()
            
            # Final validation: Ensure headers exist
            if "-----BEGIN PRIVATE KEY-----" not in fixed_key:
                fixed_key = "-----BEGIN PRIVATE KEY-----\n" + fixed_key
            if "-----END PRIVATE KEY-----" not in fixed_key:
                fixed_key = fixed_key + "\n-----END PRIVATE KEY-----"
                
            cred_info["private_key"] = fixed_key
            
            # Initialize with cleaned credentials
            cred = credentials.Certificate(cred_info)
            firebase_admin.initialize_app(cred)
        except Exception as e:
            st.error(f"⚠️ Firebase Authentication Error: {e}")
            st.info("Check your Streamlit Secrets for trailing spaces or broken TOML triple-quotes.")
            st.stop()
            
    return firestore.client()

db = init_db()

# --- 3. SESSION STATE ---
if "username" not in st.session_state: st.session_state.username = None
if "page" not in st.session_state: st.session_state.page = "login"
if "current_char" not in st.session_state: st.session_state.current_char = None

def get_user_pfp():
    if not st.session_state.username: return None
    doc = db.collection("users").document(st.session_state.username).get()
    return doc.to_dict().get("pfp") if doc.exists else None

# --- 4. NAVIGATION CONTROL ---

# --- PAGE: LOGIN ---
if st.session_state.page == "login":
    st.title("Zebra C.AI")
    st.caption("March 2026 Production Build")
    
    u_in = st.text_input("Username", placeholder="ENTER USERNAME...").strip().upper()
    if st.button("Enter Lobby"):
        if u_in:
            st.session_state.username = u_in
            st.session_state.page = "lobby"
            st.rerun()

# --- PAGE: LOBBY ---
elif st.session_state.page == "lobby":
    st.title(f"Lobby | {st.session_state.username}")
    
    with st.sidebar:
        st.header("Profile Settings")
        pfp_url = get_user_pfp()
        if pfp_url: st.image(pfp_url, width=150)
        
        up = st.file_uploader("Upload New Avatar", type=["jpg", "png"])
        if up and st.button("Update Profile"):
            new_url = upload_image(up)
            db.collection("users").document(st.session_state.username).set({"pfp": new_url}, merge=True)
            st.success("Avatar Sync Complete!")
            st.rerun()
            
        st.divider()
        if st.button("Logout"):
            st.session_state.username = None
            st.session_state.page = "login"
            st.rerun()

    st.subheader("Your AI Personas")
    if st.button("➕ Create New Persona"):
        st.session_state.page = "creator"
        st.rerun()

    # Fetch Personas from Firestore
    chars = [d.to_dict() | {"id": d.id} for d in db.collection("characters").stream()]
    
    if not chars:
        st.info("No personas found. Create your first one to start chatting!")
    
    for c in chars:
        with st.container():
            col1, col2, col3, col4 = st.columns([1, 4, 1, 1])
            with col1: st.image(c.get("pfp"), width=80)
            with col2: st.markdown(f"**{c['name']}**\n\n{c.get('description', '')[:85]}...")
            with col3: 
                if st.button("Chat", key=f"chat_{c['id']}"):
                    st.session_state.current_char = c
                    st.session_state.page = "chat"
                    st.rerun()
            with col4:
                if st.button("🗑️", key=f"del_{c['id']}"):
                    db.collection("characters").document(c['id']).delete()
                    st.rerun()

# --- PAGE: CREATOR ---
elif st.session_state.page == "creator":
    st.title("Persona Workshop")
    if st.button("← Back to Lobby"): st.session_state.page = "lobby"; st.rerun()
    
    with st.form("new_persona"):
        name = st.text_input("Name")
        desc = st.text_area("Personality / System Prompt")
        greet = st.text_area("Intro Message", placeholder="How does the AI start the conversation?")
        img_file = st.file_uploader("Character Portrait", type=["png", "jpg"])
        
        if st.form_submit_button("Initialize Persona"):
            if name and desc and img_file:
                with st.spinner("Uploading assets..."):
                    portrait_url = upload_image(img_file)
                    db.collection("characters").add({
                        "name": name, "description": desc, "intro_text": greet,
                        "pfp": portrait_url, "creator": st.session_state.username
                    })
                st.session_state.page = "lobby"; st.rerun()
            else:
                st.error("All fields are required to bring a persona to life.")

# --- PAGE: CHAT ---
elif st.session_state.page == "chat":
    char = st.session_state.current_char
    user_pfp = get_user_pfp()
    chat_id = f"{st.session_state.username}_{char['id']}"

    # Navigation & Bio Popover
    h_col1, h_col2, h_col3 = st.columns([1, 4, 1])
    h_col1.button("← Lobby", on_click=lambda: setattr(st.session_state, 'page', 'lobby'))
    h_col2.subheader(f"{char['name']}")
    
    with h_col3:
        with st.popover("👤 Profile"):
            st.image(char['pfp'], width=100)
            st.write(f"**Persona:** {char['name']}")
            st.divider()
            st.write(char['description'])

    # Chat History Rendering
    messages_ref = db.collection("chats").document(chat_id).collection("messages").order_by("timestamp").stream()
    history = [{"role": m.to_dict()["role"], "content": m.to_dict()["content"]} for m in messages_ref]

    # Initial Greeting
    if not history:
        greet_content = char.get('intro_text', "Hello!")
        db.collection("chats").document(chat_id).collection("messages").add({
            "role": "assistant", "content": greet_content, 
            "timestamp": datetime.datetime.now(datetime.timezone.utc)
        })
        st.rerun()

    for m in history:
        avatar = char['pfp'] if m['role'] == "assistant" else user_pfp
        with st.chat_message(m['role'], avatar=avatar):
            st.markdown(m['content'])

    # Message Input
    if prompt := st.chat_input(f"Message {char['name']}..."):
        # Optimistic UI: Display user message immediately
        with st.chat_message("user", avatar=user_pfp):
            st.markdown(prompt)
        
        # Save User Message
        db.collection("chats").document(chat_id).collection("messages").add({
            "role": "user", "content": prompt, "timestamp": datetime.datetime.now(datetime.timezone.utc)
        })

        # AI Turn
        with st.chat_message("assistant", avatar=char['pfp']):
            with st.spinner(f"{char['name']} is thinking..."):
                system_prompt = f"You are {char['name']}. Persona Background: {char['description']}"
                context = [{"role": "system", "content": system_prompt}]
                context += history[-15:] # Maintain a deep conversation buffer
                context.append({"role": "user", "content": prompt})
                
                ai_reply = get_ai_response(context)
                st.markdown(ai_reply)
                
                # Save Assistant Message
                db.collection("chats").document(chat_id).collection("messages").add({
                    "role": "assistant", "content": ai_reply, 
                    "timestamp": datetime.datetime.now(datetime.timezone.utc)
                })
