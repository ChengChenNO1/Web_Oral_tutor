import streamlit as st
from openai import OpenAI
import json
import base64
import asyncio
import edge_tts
import os
import tempfile
from streamlit_mic_recorder import mic_recorder

# --- 1. 页面配置 ---
st.set_page_config(page_title="AI 英语口语私教", layout="wide", initial_sidebar_state="collapsed")

# --- 2. 自定义 CSS 样式 ---
st.markdown("""
    <style>
        .stApp { background-color: #F7F8FA; }
        .main .block-container { padding-bottom: 180px; max-width: 900px; }
        .phase-card {
            background-color: white;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 15px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.03);
            border-left: 6px solid #CCC;
        }
        .phase-1 { border-left-color: #4A90E2; }
        .phase-2 { border-left-color: #50C878; background-color: #F0FFF4; }
        .phase-3 { border-left-color: #FF9F43; }
        .phase-header { font-weight: bold; font-size: 1.1rem; margin-bottom: 10px; color: #333; }
        .footer-container {
            position: fixed;
            bottom: 0; left: 0; right: 0;
            background: rgba(255, 255, 255, 0.98);
            backdrop-filter: blur(10px);
            padding: 20px 0;
            border-top: 1px solid #EEE;
            z-index: 1000;
        }
    </style>
""", unsafe_allow_html=True)

# --- 3. 安全模式：获取 API Key ---
# 逻辑：先找 Streamlit Secrets，找不到再让用户手动输入
groq_api_key = st.secrets.get("GROQ_API_KEY", "")

with st.sidebar:
    st.title("💡 教练设置")
    if not groq_api_key:
        groq_api_key = st.text_input("请输入 Groq API Key", type="password")
        st.info("可以在 https://console.groq.com/ 获取免费 Key")

    voice_choice = st.selectbox("口音选择", ["美式女声 (Ava)", "英式女声 (Sonia)", "美式男声 (Andrew)"])
    v_map = {
        "美式女声 (Ava)": "en-US-AvaMultilingualNeural",
        "英式女声 (Sonia)": "en-GB-SoniaNeural",
        "美式男声 (Andrew)": "en-US-AndrewMultilingualNeural"
    }
    input_mode = st.radio("录入模式", ["语音", "文字"])
    if st.button("🗑️ 清空记录"):
        st.session_state.messages = []
        st.rerun()

# 初始化客户端（仅在有 Key 的情况下）
groq_client = None
if groq_api_key:
    groq_client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=groq_api_key)


# --- 4. 辅助功能 ---
async def get_voice_audio(text, voice="en-US-AvaMultilingualNeural"):
    communicate = edge_tts.Communicate(text, voice)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
        tmp_path = tmp_file.name
    await communicate.save(tmp_path)
    with open(tmp_path, "rb") as f:
        data = f.read()
    b64 = base64.b64encode(data).decode()
    os.remove(tmp_path)
    return b64


def get_ai_response(user_text):
    if not groq_client: return None
    system_prompt = """
    你是一名精通中英双语的专业英语口语私教。根据用户的文本输出 JSON。
    JSON 结构要求：
    {
        "phase1_correction": "针对文本语法纠错点评，并给出中文发音指导（连读、重音等）。",
        "phase2_optimized_text": "提供修正后最完整、地道的完整英文例句（仅英文）。",
        "phase3_interaction": "先对用户内容做出自然回应（如 That's great!），再抛出相关追问延续对话。",
        "phase4_expansion": ["基础版回复参考", "进阶版回复参考"]
    }
    """
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_text}],
            response_format={"type": "json_object"},
            temperature=0.7
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        st.error(f"AI 响应出错: {e}")
        return None


# --- 5. 聊天区 ---
st.title("🎙️ AI 英语口语私教")

if not groq_api_key:
    st.warning("👈 请在左侧侧边栏配置 Groq API Key 以开始练习。")
else:
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for i, msg in enumerate(st.session_state.messages):
        if msg["role"] == "user":
            with st.chat_message("user", avatar="👤"):
                st.write(msg["content"])
        else:
            with st.chat_message("assistant", avatar="🤖"):
                data = msg["content"]
                st.markdown(
                    f'<div class="phase-card phase-1"><div class="phase-header">🔵 AI 纠错点评</div>{data["phase1_correction"]}</div>',
                    unsafe_allow_html=True)
                st.markdown(
                    f'<div class="phase-card phase-2"><div class="phase-header">🟢 AI 优化表达</div><span style="font-size:1.2rem; color:#1B5E20;"><b>{data["phase2_optimized_text"]}</b></span></div>',
                    unsafe_allow_html=True)
                st.markdown(
                    f'<div class="phase-card phase-3"><div class="phase-header">🟠 AI 互动交流</div>{data["phase3_interaction"]}</div>',
                    unsafe_allow_html=True)
                st.markdown(
                    f"<div style='padding-left:15px; margin-bottom:15px;'><small style='color:#888;'>💡 回应参考: 1️⃣ {data['phase4_expansion'][0]} | 2️⃣ {data['phase4_expansion'][1]}</small></div>",
                    unsafe_allow_html=True)

                if i == len(st.session_state.messages) - 1:
                    speech_text = f"You can say: {data['phase2_optimized_text']}. {data['phase3_interaction']}"
                    audio_b64 = asyncio.run(get_voice_audio(speech_text, v_map[voice_choice]))
                    st.markdown(
                        f'<audio src="data:audio/mp3;base64,{audio_b64}" autoplay controls style="width:100%; height:35px;"></audio>',
                        unsafe_allow_html=True)

    # --- 6. 固定底部输入区 ---
    st.markdown('<div class="footer-container">', unsafe_allow_html=True)
    cols = st.columns([1, 6, 1])
    with cols[1]:
        if input_mode == "语音":
            audio_input = mic_recorder(start_prompt="🎤 长按开始录音", stop_prompt="✅ 松开完成识别", key='recorder',
                                       use_container_width=True)
            if audio_input:
                curr_id = hash(audio_input['bytes'])
                if "last_id" not in st.session_state or st.session_state.last_id != curr_id:
                    st.session_state.last_id = curr_id
                    with st.spinner("教练正在听..."):
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                            tmp.write(audio_input['bytes'])
                            t_path = tmp.name
                        with open(t_path, "rb") as f:
                            transcript = groq_client.audio.transcriptions.create(model="whisper-large-v3", file=f)
                        os.remove(t_path)
                        user_text = transcript.text
                        if user_text.strip():
                            ai_data = get_ai_response(user_text)
                            if ai_data:
                                st.session_state.messages.append({"role": "user", "content": user_text})
                                st.session_state.messages.append({"role": "assistant", "content": ai_data})
                                st.rerun()
        else:
            t_input = st.chat_input("在输入框输入你的英语句子...")
            if t_input:
                with st.spinner("教练正在思考..."):
                    ai_data = get_ai_response(t_input)
                    if ai_data:
                        st.session_state.messages.append({"role": "user", "content": t_input})
                        st.session_state.messages.append({"role": "assistant", "content": ai_data})
                        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)