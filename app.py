import streamlit as st
from openai import OpenAI
from pypdf import PdfReader
from docx import Document
from gtts import gTTS
import tempfile
import speech_recognition as sr

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
}

for key, value in default_states.items():

    if key not in st.session_state:

        st.session_state[key] = value

# ---------------- MAX QUESTIONS ---------------- #

MAX_QUESTIONS = {
    "HR Round": 5,
    "Technical Round": 8,
    "Managerial Round": 6
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

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".mp3"
        ) as fp:

            tts.save(fp.name)

            st.audio(fp.name, format="audio/mp3")

    except Exception as e:

        st.warning(f"Voice output error: {e}")


def speech_to_text():

    recognizer = sr.Recognizer()

    try:

        with sr.Microphone() as source:

            st.info("🎙️ Listening...")

            recognizer.adjust_for_ambient_noise(source)

            audio = recognizer.listen(
                source,
                timeout=5,
                phrase_time_limit=20
            )

            text = recognizer.recognize_google(audio)

            return text

    except Exception as e:

        st.error(f"Speech recognition error: {e}")

        return None


def reset_round():

    st.session_state.messages = []

    st.session_state.question_count = 0

    st.session_state.chat_complete = False

    st.session_state.feedback_shown = False


# ---------------- CANDIDATE PROFILE ---------------- #

if not st.session_state.profile_completed:

    st.subheader("👤 Candidate Profile")

    st.session_state["name"] = st.text_input(
        "Candidate Name"
    )

    st.session_state["experience"] = st.text_area(
        "Experience"
    )

    st.session_state["skills"] = st.text_area(
        "Skills"
    )

    # ---------------- RESUME UPLOAD ---------------- #

    st.subheader("📄 Upload Resume")

    uploaded_resume = st.file_uploader(
        "Upload Resume (PDF preferred)",
        type=["pdf", "docx"]
    )

    if uploaded_resume:

        resume_text = extract_resume_text(
            uploaded_resume
        )

        st.session_state["resume_text"] = resume_text

        st.success("✅ Resume uploaded successfully")

    # ---------------- INTERVIEW CONFIG ---------------- #

    st.subheader("💼 Interview Configuration")

    col1, col2 = st.columns(2)

    with col1:

        st.session_state["level"] = st.selectbox(
            "Experience Level",
            ["Junior", "Mid-Level", "Senior"]
        )

    with col2:

        st.session_state["difficulty"] = st.selectbox(
            "Difficulty",
            ["Easy", "Medium", "Hard"]
        )

    st.session_state["company"] = st.text_input(
        "Company Name",
        placeholder="Google, Nvidia, Qualcomm..."
    )

    st.session_state["position"] = st.text_input(
        "Job Position",
        placeholder="ML Engineer, Embedded Engineer..."
    )

    st.session_state["round_type"] = st.selectbox(
        "Interview Round",
        [
            "HR Round",
            "Technical Round",
            "Managerial Round"
        ]
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

        Focus on:
        - self introduction
        - communication
        - career goals
        - salary expectations
        - notice period
        - why candidate wants to join company

        Avoid:
        - technical deep dive
        - leadership scenarios
        """

    elif round_type == "Technical Round":

        round_prompt = """
        Ask ONLY technical questions.

        Focus on:
        - resume projects
        - debugging
        - coding concepts
        - optimization
        - technical scenarios
        - system design

        Avoid:
        - salary discussion
        - HR questions
        """

    else:

        round_prompt = """
        Ask ONLY managerial questions.

        Focus on:
        - leadership
        - ownership
        - conflict resolution
        - collaboration
        - mentoring
        - decision making
        - deadline management

        Avoid:
        - salary discussion
        - technical deep dive
        """

    # ---------------- INITIAL SYSTEM PROMPT ---------------- #

    if not st.session_state.messages:

        system_prompt = f"""
        You are a professional interviewer.

        Interview Round:
        {round_type}

        Candidate Name:
        {st.session_state['name']}

        Experience:
        {st.session_state['experience']}

        Skills:
        {st.session_state['skills']}

        Resume:
        {st.session_state.get('resume_text', '')}

        Company:
        {st.session_state['company']}

        Position:
        {st.session_state['position']}

        Experience Level:
        {st.session_state['level']}

        Difficulty:
        {st.session_state['difficulty']}

        Instructions:
        {round_prompt}

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

        greeting = f"""
        Welcome to the {round_type}.

        Please introduce yourself.
        """

        st.session_state.messages.append({
            "role": "assistant",
            "content": greeting
        })

    # ---------------- DISPLAY CHAT ---------------- #

    for message in st.session_state.messages:

        if message["role"] != "system":

            with st.chat_message(message["role"]):

                st.markdown(message["content"])

    # ---------------- SPEAK LAST AI RESPONSE ---------------- #

    if (
        st.session_state.messages[-1]["role"]
        == "assistant"
    ):

        speak_text(
            st.session_state.messages[-1]["content"]
        )

    # ---------------- OPTIONAL VOICE INPUT ---------------- #

    st.subheader("🎙️ Optional Voice Input")

    if st.button("Speak Answer"):

        voice_text = speech_to_text()

        if voice_text:

            st.success(f"You said: {voice_text}")

            st.session_state.voice_prompt = voice_text

    # ---------------- TEXT INPUT ---------------- #

    typed_prompt = st.chat_input(
        "Type your answer"
    )

    prompt = None

    if typed_prompt:

        prompt = typed_prompt

    elif "voice_prompt" in st.session_state:

        prompt = st.session_state.voice_prompt

        del st.session_state.voice_prompt

    # ---------------- USER RESPONSE ---------------- #

    if prompt:

        st.session_state.messages.append({
            "role": "user",
            "content": prompt
        })

        with st.chat_message("user"):

            st.markdown(prompt)

        # ---------------- QUESTION COUNT ---------------- #

        st.session_state.question_count += 1

        # ---------------- CHECK ROUND COMPLETION ---------------- #

        if (
            st.session_state.question_count
            >= MAX_QUESTIONS[round_type]
        ):

            ending_message = f"""
            Thank you for attending the {round_type}.

            We appreciate your time and responses.
            """

            with st.chat_message("assistant"):

                st.markdown(ending_message)

            st.session_state.messages.append({
                "role": "assistant",
                "content": ending_message
            })

            speak_text(ending_message)

            st.session_state.chat_complete = True

        else:

            # ---------------- AI RESPONSE ---------------- #

            with st.chat_message("assistant"):

                stream = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[
                        {
                            "role": m["role"],
                            "content": m["content"]
                        }
                        for m in st.session_state.messages
                    ],
                    stream=True
                )

                response = st.write_stream(stream)

            st.session_state.messages.append({
                "role": "assistant",
                "content": response
            })

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
                "content":
                "You are an expert interview evaluator."
            },
            {
                "role": "user",
                "content": feedback_prompt
            }
        ]
    )

    st.write(
        feedback_response.choices[0].message.content
    )

    # ---------------- NEXT ROUND ---------------- #

    st.subheader("➡️ Continue Interview")

    next_round = st.selectbox(
        "Choose Next Round",
        [
            "HR Round",
            "Technical Round",
            "Managerial Round"
        ]
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