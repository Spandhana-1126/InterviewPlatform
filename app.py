import streamlit as st
from openai import OpenAI
from pypdf import PdfReader
from docx import Document
from gtts import gTTS
from audio_recorder_streamlit import audio_recorder
import tempfile
import os
import re
import time

# ---------------- PAGE CONFIG ---------------- #

st.set_page_config(
    page_title="Interview Platform",
    layout="centered"
)

st.title("Interview Platform")

# ---------------- SESSION STATES ---------------- #

default_states = {
    "profile_completed": False,
    "chat_complete": False,
    "feedback_shown": False,
    "messages": [],
    "question_count": 0,
    "audio_key": 0,
    "last_spoken_index": -1,
    "last_audio_bytes": None,   # FIX 1: track previous audio to prevent re-trigger
    "stop_triggered": False,    # STOP BUTTON: tracks early exit
}

for key, value in default_states.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ---------------- MAX QUESTIONS ---------------- #

MAX_QUESTIONS = {
    "HR Round": 5,
    "Technical Round": 8,
    "Managerial Round": 5
}

# ---------------- OPENAI CLIENT ---------------- #

client = OpenAI(
    api_key=st.secrets["GROQ_API_KEY"],
    base_url="https://api.groq.com/openai/v1"
)

MODEL_NAME = "llama-3.1-8b-instant"

# ---------------- FUNCTIONS ---------------- #

def extract_resume_text(uploaded_file):
    text = ""
    if uploaded_file.type == "application/pdf":
        pdf_reader = PdfReader(uploaded_file)
        for page in pdf_reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
    elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        doc = Document(uploaded_file)
        for para in doc.paragraphs:
            text += para.text + "\n"
    return text.strip()


# FIX 6: Strip markdown symbols before passing to gTTS
def strip_markdown(text):
    text = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', text)   # bold / italic
    text = re.sub(r'#{1,6}\s*', '', text)                  # headings
    text = re.sub(r'`{1,3}[^`]*`{1,3}', '', text)         # code blocks
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)  # links
    text = re.sub(r'[-*_]{3,}', '', text)                  # horizontal rules
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)  # bullet points
    text = re.sub(r'\n{2,}', '. ', text)                   # double newlines to pause
    text = text.strip()
    return text


# FIX 2: gTTS retry with fallback warning on internet failure
def speak_text(text):
    clean_text = strip_markdown(text)   # FIX 6 applied here
    for attempt in range(2):
        try:
            tts = gTTS(clean_text)
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=".mp3"
            ) as fp:
                tmp_path = fp.name
                tts.save(tmp_path)
            st.audio(tmp_path, format="audio/mp3")
            # cleanup temp file after use
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            return
        except Exception as e:
            if attempt == 0:
                time.sleep(1)   # wait 1 sec before retry
            else:
                st.warning(
                    "⚠️ Voice playback unavailable (network issue). "
                    "Please read the text above."
                )


def transcribe_audio(audio_bytes):
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=".wav"
        ) as tmp_audio:
            tmp_audio.write(audio_bytes)
            tmp_path = tmp_audio.name
        with open(tmp_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                file=audio_file,
                model="whisper-large-v3"
            )
        return transcription.text
    finally:
        # cleanup temp file
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def reset_round():
    st.session_state.messages = []
    st.session_state.question_count = 0
    st.session_state.chat_complete = False
    st.session_state.feedback_shown = False
    st.session_state.audio_key += 1
    st.session_state.last_spoken_index = -1
    st.session_state.last_audio_bytes = None  # FIX 1: clear on reset
    st.session_state.stop_triggered = False


# ---------------- PROFILE SECTION ---------------- #

if not st.session_state.profile_completed:

    st.subheader("👤 Candidate Profile")

    st.session_state["name"] = st.text_input("Candidate Name")
    st.session_state["experience"] = st.text_area("Experience")
    st.session_state["skills"] = st.text_area("Skills")

    st.subheader("📄 Upload Resume")

    uploaded_resume = st.file_uploader("Upload Resume", type=["pdf", "docx"])

    if uploaded_resume:
        resume_text = extract_resume_text(uploaded_resume)
        st.session_state["resume_text"] = resume_text

        # FIX 4: Warn user if resume text is empty (scanned/image PDF)
        if not resume_text:
            st.error(
                "⚠️ Could not extract text from your resume. "
                "It may be a scanned or image-based PDF. "
                "Please upload a text-based PDF or DOCX file. "
                "The interview will rely only on the Experience and Skills fields you filled above."
            )
        else:
            st.success("✅ Resume uploaded and text extracted successfully.")

    st.subheader("💼 Interview Configuration")

    col1, col2 = st.columns(2)
    with col1:
        st.session_state["level"] = st.selectbox(
            "Experience Level", ["Junior", "Mid-Level", "Senior"]
        )
    with col2:
        st.session_state["difficulty"] = st.selectbox(
            "Difficulty", ["Easy", "Medium", "Hard"]
        )

    st.session_state["company"] = st.text_input(
        "Company Name", placeholder="Google, Nvidia, Qualcomm..."
    )
    st.session_state["position"] = st.text_input(
        "Job Position", placeholder="ML Engineer, Embedded Engineer..."
    )
    st.session_state["round_type"] = st.selectbox(
        "Interview Round", ["HR Round", "Technical Round", "Managerial Round"]
    )

    if st.button("🚀 Start Interview"):
        st.session_state.profile_completed = True
        st.rerun()


# ---------------- INTERVIEW SECTION ---------------- #

if (
    st.session_state.profile_completed
    and not st.session_state.chat_complete
):
    round_type = st.session_state["round_type"]

    # ---------------- ROUND PROMPTS ---------------- #

    if round_type == "HR Round":
        round_prompt = """
        Ask ONLY HR-related questions.
        Focus on: self introduction, communication, career goals,
        salary expectations, current CTC, expected CTC, notice period,
        why candidate wants to join company.
        You MUST include at least one salary discussion question.
        Avoid: technical deep dive, leadership scenarios.
        """
    elif round_type == "Technical Round":
        round_prompt = """
        Ask ONLY technical questions.
        Focus on: resume projects, debugging, coding concepts,
        optimization, technical scenarios, system design.
        Avoid: salary discussion, HR questions.
        """
    else:
        round_prompt = """
        Ask ONLY managerial questions.
        Focus on: leadership, ownership, conflict resolution,
        collaboration, mentoring, decision making, deadline management.
        Avoid: salary discussion, technical deep dive.
        """

    # ---------------- SYSTEM PROMPT ---------------- #

    if not st.session_state.messages:
        system_prompt = f"""
        You are a strict, professional interviewer.

        Interview Round: {round_type}
        Candidate Name: {st.session_state['name']}
        Experience: {st.session_state['experience']}
        Skills: {st.session_state['skills']}
        Resume (ONLY source of truth for candidate background):
        {st.session_state.get('resume_text', '')}
        Company: {st.session_state['company']}
        Position: {st.session_state['position']}
        Experience Level: {st.session_state['level']}
        Difficulty: {st.session_state['difficulty']}

        Instructions: {round_prompt}

        STRICT ANTI-HALLUCINATION RULES (NON-NEGOTIABLE):
        - ONLY ask about projects, skills, tools, and technologies explicitly in the Resume above.
        - Do NOT invent, assume, or guess any project or experience NOT written in the resume.
        - Do NOT say "I see you worked on X" unless X is literally in the resume text.
        - If the resume is empty, ask only about the skills and experience fields provided.
        - Never fabricate project names, company names, tools, or roles.
        - If unsure whether something is in the resume, DO NOT ask about it.

        INTERVIEW RULES:
        - Ask one question at a time
        - Avoid repeated questions
        - Behave like a real interviewer
        - Ask natural follow-up questions based only on what the candidate actually says
        - Gradually increase difficulty
        - Keep interview professional
        - Do NOT use markdown formatting like ** or ## in your responses — plain text only.
        """

        st.session_state.messages.append({
            "role": "system",
            "content": system_prompt
        })

        greeting = f"Welcome to the {round_type}. Please introduce yourself."

        st.session_state.messages.append({
            "role": "assistant",
            "content": greeting
        })

    # ---------------- DISPLAY CHAT ---------------- #

    for message in st.session_state.messages:
        if message["role"] != "system":
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    # ---------------- SPEAK LATEST AI RESPONSE (only once) ---------------- #

    all_messages = st.session_state.messages
    last_index = len(all_messages) - 1

    if (
        all_messages[last_index]["role"] == "assistant"
        and last_index != st.session_state.last_spoken_index
    ):
        speak_text(all_messages[last_index]["content"])
        st.session_state.last_spoken_index = last_index

    # ---------------- STOP BUTTON ---------------- #

    stop_col, _ = st.columns([2, 8])
    with stop_col:
        if st.button(
            "⏹ Stop Interview",
            key="stop_btn",
            type="secondary",
            use_container_width=True
        ):
            st.session_state.stop_triggered = True

    if st.session_state.stop_triggered:
        # Only stop if at least one answer has been given
        user_answers = [
            m for m in st.session_state.messages
            if m["role"] == "user"
        ]
        if user_answers:
            early_stop_message = (
                "You have chosen to end the interview early. "
                "Thank you for your time. "
                "Feedback will be generated based on your answers so far."
            )
            with st.chat_message("assistant"):
                st.markdown(early_stop_message)
            st.session_state.messages.append({
                "role": "assistant",
                "content": early_stop_message
            })
            st.session_state.chat_complete = True
            st.session_state.stop_triggered = False
            st.rerun()
        else:
            st.warning(
                "⚠️ Please answer at least one question before stopping. "
                "There won't be enough data to generate feedback."
            )
            st.session_state.stop_triggered = False

    # ---------------- INPUT AREA ---------------- #
    # FIX: Mic icon placed inside chat_input bar using custom CSS overlay

    st.markdown("""
        <style>
        /* Push mic button to sit right of the chat input box */
        div[data-testid="stChatInput"] {
            position: relative;
        }
        .mic-wrapper {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 4px;
        }
        .mic-label {
            color: gray;
            font-size: 0.85rem;
            margin: 0;
        }
        </style>
    """, unsafe_allow_html=True)

    # Mic row — sits directly above the chat input bar, right-aligned feel
    st.markdown('<div class="mic-wrapper">', unsafe_allow_html=True)
    mic_col, spacer_col = st.columns([1, 11])
    with mic_col:
        # FIX 1: rotating key prevents re-trigger; compare bytes to last recorded
        audio_bytes = audio_recorder(
            text="",
            recording_color="#e74c3c",
            neutral_color="#2c2c2c",
            icon_name="microphone",
            icon_size="lg",
            key=f"audio_recorder_{st.session_state.audio_key}"
        )
    with spacer_col:
        st.markdown(
            "<p class='mic-label'>🎙️ Record answer with mic, or type below</p>",
            unsafe_allow_html=True
        )
    st.markdown('</div>', unsafe_allow_html=True)

    voice_prompt = None

    # FIX 1: Only process audio if it's NEW bytes (not a rerun of old bytes)
    if audio_bytes and audio_bytes != st.session_state.last_audio_bytes:
        st.session_state.last_audio_bytes = audio_bytes
        with st.spinner("Transcribing your voice..."):
            try:
                voice_prompt = transcribe_audio(audio_bytes)
                st.success(f"🎤 Transcribed: *{voice_prompt}*")
            except Exception as e:
                st.error(f"Transcription error: {e}")

    # chat_input at root level (Streamlit requirement)
    typed_prompt = st.chat_input("Type your answer here...")

    prompt = typed_prompt or voice_prompt

    # ---------------- USER RESPONSE ---------------- #

    if prompt:

        with st.chat_message("user"):
            st.markdown(prompt)

        st.session_state.messages.append({
            "role": "user",
            "content": prompt
        })

        # rotate audio key so mic resets for next question
        st.session_state.audio_key += 1
        st.session_state.last_audio_bytes = None   # FIX 1: clear so next recording is fresh

        # ---------------- INTERVIEW COMPLETE ---------------- #

        if st.session_state.question_count >= MAX_QUESTIONS[round_type]:

            ending_message = (
                f"Thank you for attending the {round_type}. "
                "We appreciate your time and responses. "
                "Please click below to generate your interview feedback."
            )

            with st.chat_message("assistant"):
                st.markdown(ending_message)

            st.session_state.messages.append({
                "role": "assistant",
                "content": ending_message
            })

            st.session_state.chat_complete = True
            st.rerun()

        else:

            questions_remaining = MAX_QUESTIONS[round_type] - st.session_state.question_count
            control_note = {
                "role": "system",
                "content": (
                    f"IMPORTANT: You have asked {st.session_state.question_count} questions so far. "
                    f"You may ask {questions_remaining} more question(s) in this round. "
                    f"Total allowed: {MAX_QUESTIONS[round_type]}. "
                    "Ask only ONE question in your next reply. "
                    "Do NOT use markdown formatting — plain text only."
                )
            }

            messages_with_control = [
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.messages
            ] + [control_note]

            with st.chat_message("assistant"):
                stream = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=messages_with_control,
                    stream=True
                )
                response = st.write_stream(stream)

            st.session_state.messages.append({
                "role": "assistant",
                "content": response
            })

            st.session_state.question_count += 1
            st.rerun()


# ---------------- FEEDBACK SECTION ---------------- #

if (
    st.session_state.chat_complete
    and not st.session_state.feedback_shown
):
    st.success("✅ Interview Round Completed")

    if st.button("📋 Generate Feedback"):
        st.session_state.feedback_shown = True
        st.rerun()


# ---------------- FEEDBACK GENERATION ---------------- #

if st.session_state.feedback_shown:

    st.subheader("📊 Interview Feedback")

    # FIX 7 (partial): filter out system messages from feedback — cleaner + saves tokens
    conversation_history = "\n".join([
        f"{msg['role'].upper()}: {msg['content']}"
        for msg in st.session_state.messages
        if msg["role"] != "system"
    ])

    feedback_prompt = f"""
    Evaluate this interview professionally.
    Provide:
    1. Overall Score (1-10)
    2. Communication Evaluation
    3. Technical Evaluation
    4. Leadership / Behavioral Evaluation
    5. Strengths
    6. Areas for Improvement
    7. Hiring Recommendation

    Interview Conversation:
    {conversation_history}
    """

    feedback_response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": "You are an expert interview evaluator."
            },
            {
                "role": "user",
                "content": feedback_prompt
            }
        ]
    )

    feedback_text = feedback_response.choices[0].message.content
    st.write(feedback_text)
    speak_text("Your interview feedback is ready.")

    # FIX 7: Save session to file so progress survives refresh
    import json
    session_data = {
        "name": st.session_state.get("name", ""),
        "round_type": st.session_state.get("round_type", ""),
        "question_count": st.session_state.get("question_count", 0),
        "feedback": feedback_text,
    }
    session_json = json.dumps(session_data, indent=2)
    st.download_button(
        label="💾 Download Session & Feedback",
        data=session_json,
        file_name="interview_session.json",
        mime="application/json"
    )

    # ---------------- NEXT ROUND ---------------- #

    st.subheader("➡️ Continue Interview")

    next_round = st.selectbox(
        "Choose Next Round",
        ["HR Round", "Technical Round", "Managerial Round"]
    )

    if st.button("🚀 Start Next Round"):
        st.session_state["round_type"] = next_round
        reset_round()
        st.rerun()

    if st.button("🔄 Reset Entire Interview"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
