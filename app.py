import streamlit as st
from openai import OpenAI
from pypdf import PdfReader
from docx import Document
from gtts import gTTS
from audio_recorder_streamlit import audio_recorder
import tempfile

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
    "audio_key": 0,               # FIX: rotating key to reset mic after each use
    "last_spoken_index": -1,      # FIX: track which message was last spoken
}

for key, value in default_states.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ---------------- MAX QUESTIONS ---------------- #

MAX_QUESTIONS = {
    "HR Round": 5,        # 4-5 questions including salary discussion
    "Technical Round": 8, # 8 technical questions
    "Managerial Round": 5 # 5 managerial questions
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
    return text


def speak_text(text):
    try:
        tts = gTTS(text)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            tts.save(fp.name)
            st.audio(fp.name, format="audio/mp3")
    except Exception as e:
        st.warning(f"Voice output error: {e}")


def transcribe_audio(audio_bytes):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_audio:
        tmp_audio.write(audio_bytes)
        tmp_audio_path = tmp_audio.name
    with open(tmp_audio_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            file=audio_file,
            model="whisper-large-v3"
        )
    return transcription.text


def reset_round():
    st.session_state.messages = []
    st.session_state.question_count = 0
    st.session_state.chat_complete = False
    st.session_state.feedback_shown = False
    st.session_state.audio_key += 1       # FIX: reset mic widget
    st.session_state.last_spoken_index = -1


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
        st.success("✅ Resume uploaded successfully")

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
        You are a professional interviewer.
        Interview Round: {round_type}
        Candidate Name: {st.session_state['name']}
        Experience: {st.session_state['experience']}
        Skills: {st.session_state['skills']}
        Resume: {st.session_state.get('resume_text', '')}
        Company: {st.session_state['company']}
        Position: {st.session_state['position']}
        Experience Level: {st.session_state['level']}
        Difficulty: {st.session_state['difficulty']}
        Instructions: {round_prompt}
        Rules:
        - Ask one question at a time
        - Avoid repeated questions
        - Behave like a real interviewer
        - Ask natural follow-up questions
        - Gradually increase difficulty
        - Keep interview professional
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
    # FIX: Only speak when there's a new assistant message we haven't spoken yet

    all_messages = st.session_state.messages
    last_index = len(all_messages) - 1

    if (
        all_messages[last_index]["role"] == "assistant"
        and last_index != st.session_state.last_spoken_index
    ):
        speak_text(all_messages[last_index]["content"])
        st.session_state.last_spoken_index = last_index

    # ---------------- INPUT AREA ---------------- #
    # FIX: st.chat_input must be at the top level (not inside columns)
    # We place the mic button above it using st.columns in the main body

    st.markdown("---")
    st.markdown("### 💬 Your Response")

    # Mic recorder — key rotates after each submission to reset the widget
    mic_col, label_col = st.columns([1, 6])

    with mic_col:
        audio_bytes = audio_recorder(
            text="",
            recording_color="#e74c3c",
            neutral_color="#6c757d",
            icon_name="microphone",
            icon_size="2x",
            key=f"audio_recorder_{st.session_state.audio_key}"  # FIX: rotating key
        )

    with label_col:
        st.markdown(
            "<p style='margin-top:12px; color:gray;'>🎙️ Click mic to record your answer, or type below</p>",
            unsafe_allow_html=True
        )

    voice_prompt = None

    if audio_bytes:
        with st.spinner("Transcribing your voice..."):
            try:
                voice_prompt = transcribe_audio(audio_bytes)
                st.success(f"🎤 Transcribed: *{voice_prompt}*")
            except Exception as e:
                st.error(f"Transcription error: {e}")

    # FIX: chat_input placed at the top level — outside any column
    typed_prompt = st.chat_input("Type your answer here...")

    # ---------------- FINAL PROMPT ---------------- #

    prompt = typed_prompt or voice_prompt

    # ---------------- USER RESPONSE ---------------- #

    if prompt:

        with st.chat_message("user"):
            st.markdown(prompt)

        st.session_state.messages.append({
            "role": "user",
            "content": prompt
        })

        # FIX: rotate audio key so mic resets for the next question
        st.session_state.audio_key += 1

        # ---------------- INTERVIEW COMPLETE ---------------- #
        # question_count tracks AI questions asked (incremented after each AI reply)

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

            # Tell AI how many questions remain so it doesn't go infinite
            questions_remaining = MAX_QUESTIONS[round_type] - st.session_state.question_count
            control_note = {
                "role": "system",
                "content": (
                    f"IMPORTANT: You have asked {st.session_state.question_count} questions so far. "
                    f"You may ask {questions_remaining} more question(s) in this round. "
                    f"Total allowed: {MAX_QUESTIONS[round_type]}. "
                    "Ask only ONE question in your next reply. Do NOT ask more than one question at a time."
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

            # FIX: increment question count AFTER AI asks a question
            st.session_state.question_count += 1

            st.rerun()  # rerun so speak_text fires cleanly via last_spoken_index logic


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

    conversation_history = "\n".join([
        f"{msg['role']}: {msg['content']}"
        for msg in st.session_state.messages
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

    # ---------------- FULL RESET ---------------- #

    if st.button("🔄 Reset Entire Interview"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
