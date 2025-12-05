import streamlit as st
import os
import google.generativeai as genai
from dotenv import load_dotenv
import tempfile
import base64
import time
import uuid
from datetime import datetime
import session_manager
from streamlit_pdf_viewer import pdf_viewer

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(layout="wide", page_title="Local Alphaxiv")

# Title
st.title("Local Alphaxiv")

# Initialize session state for system prompt before sidebar
if "system_prompt_val" not in st.session_state:
    st.session_state.system_prompt_val = "Analyze this paper."

# Sidebar for API Key and Sessions
with st.sidebar:
    st.header("Settings")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        api_key = st.text_input("Enter Gemini API Key", type="password")
    
    selected_model = None
    if api_key:
        os.environ["GEMINI_API_KEY"] = api_key
        try:
            genai.configure(api_key=api_key)
            st.success("API Key configured")

            # Fetch available models
            try:
                models = list(genai.list_models())
                # Filter models that support generateContent
                available_models = [
                    m.name for m in models 
                    if 'generateContent' in m.supported_generation_methods
                ]
                # Sort for better UX, maybe prefer gemini-1.5 variants at top if available
                available_models.sort(reverse=True)
                
                if not available_models:
                     st.error("No suitable models found.")
                     selected_model = None
                else:
                    # Default to gemini-1.5-flash if available, otherwise first one
                    # Logic: Prioritize "gemini-2.5-flash" (if user insists) -> "gemini-1.5-flash" -> other 1.5 variants
                    default_index = 0
                    priority_models = ["gemini-2.5-flash", "gemini-1.5-flash"]
                    
                    found = False
                    for p_model in priority_models:
                        for i, m in enumerate(available_models):
                            if p_model in m:
                                default_index = i
                                found = True
                                break
                        if found:
                            break
                    
                    selected_model = st.selectbox(
                        "Select Gemini Model", 
                        available_models, 
                        index=default_index
                    )
            except Exception as e:
                st.error(f"Error listing models: {e}")
                selected_model = "gemini-1.5-flash" # Fallback

        except Exception as e:
            st.error(f"Error configuring API Key: {e}")
            selected_model = None
    else:
        st.warning("Please configure your Gemini API Key")
        selected_model = None
    
    st.divider()
    system_prompt = st.text_area("System Prompt", value=st.session_state.system_prompt_val, height=100)
    
    st.divider()

    # Session Management Functions
    def new_chat():
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.chat_history = []
        st.session_state.summary = None
        st.session_state.gemini_file = None
        st.session_state.chat_session = None
        st.session_state.current_file_path = None
        st.session_state.system_prompt_val = "Analyze this paper."
        # Rerun to clear UI
        # st.rerun() # Called via callback usually

    def load_chat_session(session_id):
        data = session_manager.load_session(session_id)
        if data:
            st.session_state.session_id = session_id
            st.session_state.chat_history = data.get("chat_history", [])
            st.session_state.summary = data.get("summary", None)
            st.session_state.current_file_path = data.get("pdf_path", None)
            st.session_state.system_prompt_val = data.get("system_prompt", "Analyze this paper.")
            
            # Reset gemini_file and chat_session so they get re-created with the loaded file
            st.session_state.gemini_file = None
            st.session_state.chat_session = None

    if st.button("New Chat", type="primary", on_click=new_chat):
        pass # Action handled in callback

    st.subheader("Saved Sessions")
    sessions = session_manager.list_sessions()
    for s in sessions:
        if st.button(f"{s['preview']} ({s['timestamp'][:10]})", key=s['id']):
            load_chat_session(s['id'])
            st.rerun()

# Initialize session state variables if not present
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "summary" not in st.session_state:
    st.session_state.summary = None
if "gemini_file" not in st.session_state:
    st.session_state.gemini_file = None # This is the Gemini File object
if "chat_session" not in st.session_state:
    st.session_state.chat_session = None
if "current_file_path" not in st.session_state:
    st.session_state.current_file_path = None # Local path to the PDF


def display_pdf(file_path):
    """Displays PDF in Streamlit using streamlit-pdf-viewer"""
    try:
        # pdf_viewer(input, width=None, height=None, key=None, annotations=None)
        # We can specify height to make it scrollable within a container, 
        # but typically just calling it renders the PDF pages.
        # User requested continuous vertical scrolling, which this component usually does by rendering pages as canvas/img.
        pdf_viewer(file_path, height=800) 
    except FileNotFoundError:
        st.error("File not found. It may have been deleted.")

def upload_to_gemini(path, mime_type="application/pdf"):
    """Uploads the given file to Gemini."""
    file = genai.upload_file(path, mime_type=mime_type)
    # Verify that the file has uploaded
    while file.state.name == "PROCESSING":
        time.sleep(1)
        file = genai.get_file(file.name)
    if file.state.name == "FAILED":
        raise ValueError(file.state.name)
    return file

col1, col2 = st.columns([1, 1])

with col1:
    st.header("Document & Summary")
    uploaded_file = st.file_uploader("Upload a PDF", type=["pdf"])
    
    # Determine which file to process
    active_file_path = None
    
    if uploaded_file:
        # User uploaded a new file
        # Check if it is different from what we have stored
        # We will save it to a new temp file or overwrite
        # For simplicity, we always save uploaded file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            active_file_path = tmp_file.name
        
        # If this is a NEW file (different from session), we reset logic
        if st.session_state.current_file_path != active_file_path:
             st.session_state.current_file_path = active_file_path
             # Reset Gemini file to force re-upload
             st.session_state.gemini_file = None
    
    elif st.session_state.current_file_path and os.path.exists(st.session_state.current_file_path):
        # Fallback to loaded session file
        active_file_path = st.session_state.current_file_path

    # Process File
    if active_file_path and api_key:
        # If we don't have a gemini file handle yet (or we reset it), upload and init
        if not st.session_state.gemini_file:
             with st.spinner("Uploading to Gemini and generating summary..."):
                try:
                    # Upload to Gemini
                    gemini_file = upload_to_gemini(active_file_path)
                    st.session_state.gemini_file = gemini_file
                    
                    # Initialize chat session
                    model_name = selected_model if selected_model else "gemini-1.5-flash"
                    model = genai.GenerativeModel(model_name)
                    
                    # Use system prompt
                    initial_history = [
                         {
                                "role": "user",
                                "parts": [gemini_file, system_prompt]
                         },
                         {
                                "role": "model",
                                "parts": ["I have analyzed the paper based on your instructions. What would you like to know?"]
                        }
                    ]
                    
                    st.session_state.chat_session = model.start_chat(history=initial_history)
                    
                    # Generate Summary if not present (e.g. new upload)
                    if not st.session_state.summary:
                        summary_req = "Summarize this paper in a detailed, engaging blog post format. Use markdown for formatting."
                        response = st.session_state.chat_session.send_message(summary_req)
                        st.session_state.summary = response.text
                    
                    # If loading a session, restore chat history in the model context
                    # Just setting chat_session history to the initial state isn't enough if there were previous messages.
                    # We need to append the stored chat history to the model's history.
                    if st.session_state.chat_history:
                        for msg in st.session_state.chat_history:
                            # We can't directly append to chat_session.history easily in the python lib without sending messages?
                            # Actually, we can assign to history.
                            # But safer is to recreate the chat session with full history.
                            pass
                        
                        full_history = list(initial_history)
                        for msg in st.session_state.chat_history:
                            full_history.append({
                                "role": "user" if msg["role"] == "user" else "model",
                                "parts": [msg["content"]]
                            })
                        st.session_state.chat_session = model.start_chat(history=full_history)

                except Exception as e:
                    st.error(f"An error occurred: {e}")

        # Tabs for PDF and Summary
        tab1, tab2 = st.tabs(["📄 PDF Viewer", "📝 Summary"])
        
        with tab1:
            display_pdf(active_file_path)
        
        with tab2:
            if st.session_state.summary:
                st.markdown(st.session_state.summary)
            else:
                st.info("Summary will appear here after processing.")

with col2:
    st.header("Chat")
    
    if st.session_state.chat_session:
        # Display chat history
        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        # Chat input
        if prompt := st.chat_input("Ask a question about the paper"):
            # Add user message to state
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            # Generate response
            with st.spinner("Thinking..."):
                try:
                    response = st.session_state.chat_session.send_message(prompt)
                    answer = response.text
                    
                    # Add assistant response to state
                    st.session_state.chat_history.append({"role": "assistant", "content": answer})
                    with st.chat_message("assistant"):
                        st.markdown(answer)
                    
                    # Save Session
                    session_data = {
                        "timestamp": datetime.now().isoformat(),
                        "title": st.session_state.chat_history[0]["content"][:50] if st.session_state.chat_history else "New Chat",
                        "pdf_path": st.session_state.current_file_path,
                        "chat_history": st.session_state.chat_history,
                        "summary": st.session_state.summary,
                        "system_prompt": system_prompt
                    }
                    session_manager.save_session(st.session_state.session_id, session_data)

                except Exception as e:
                    st.error(f"Error generating response: {e}")
    
    elif not api_key:
        st.info("Please set your API Key to start.")
    else:
        st.info("Please upload a PDF to start chatting.")
