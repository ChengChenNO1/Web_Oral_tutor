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

# --- 2. CSS 样式 ---
st.markdown("""
    <style>
        .stApp { background-color: #F7F8FA; }
        .main .block-container { padding-bottom: 180px; max-width: 900px; }
        .phase-card {
            background-color: white; border-radius: 12px; padding: 20px;
            margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.03); border-left: 6px solid #CCC;
        }
        .phase-1 { border-left-color: #4A90E2; }
        .phase-2 { border-left-color: #50C878; background-color: #F0FFF4; }
        .phase-3 { border-left-color: #FF9F43; }
        .phase-header { font-weight: bold; font-size: 1.1rem; margin-bottom: 10px; color: #333; }
        .footer-container {
            position: fixed; bottom: 0; left: 0; right: 0;
            background: rgba(255, 255, 255, 0.98); backdrop-filter: blur(10px);
            padding: 20px 0; border-top: 1px solid #EEE; z-index: 1000;
        }
        /* 紧凑型音频条样式 */
        audio { height: 30px; width: 100%; margin-top: 8px; }
    </style>
""", unsafe_allow_html=True)

# --- 3. 密钥与状态初始化 ---
groq_api_key = st.secrets.get("GROQ_API_KEY", "")

if "messages" not in st.session_state: st.session_state.messages = []
if "last_played_id" not in st.session_state: st.session_state.last_played_id = None

# --- 4. 侧边栏 ---
with st.sidebar:
    st.title("💡 教练设置")
    if not groq_api_key:
        groq_api_key = st.text_input("请输入 Groq API Key", type="password")
    
    voice_choice = st.selectbox("口音选择", ["美式女声 (Ava)", "英式女声 (Sonia)", "美式男声 (Andrew)"])
    v_map = {
        "美式女声 (Ava)": "en-US-AvaMultilingualNeural", 
        "英式女声 (Sonia)": "en-GB-SoniaNeural", 
        "美式男声 (Andrew)": "en-US-AndrewMultilingualNeural"
    }
    input_mode = st.radio("录入模式", ["语音", "文字"])
    if st.button("🗑️ 清空历史"):
        st.session_state.messages = []
        st.session_state.last_played_id = None
        st.rerun()

groq_client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=groq_api_key) if groq_api_key else None

# --- 5. 核心功能 ---
async def get_voice_audio(text, voice="en-US-AvaMultilingualNeural"):
    if not text or len(text.strip()) == 0: return ""
    communicate = edge_tts.Communicate(text, voice)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        tmp_path = tmp.name
    await communicate.save(tmp_path)
    with open(tmp_path, "rb") as f: data = f.read()
    os.remove(tmp_path)
    return base64.b64encode(data).decode()

def get_ai_response(user_text):
    system_prompt = """
    你现在拥有双重身份，请严格按顺序执行：
    1. 【身份：专业导师】
       - phase1_correction: 针对用户的文本纠错和发音指导（中文）。
       - phase2_optimized_text: 提供一个最地道的优化例句（英文）。
    2. 【身份：知心朋友】
       - phase3_interaction: 忘掉老师身份！现在你在平等聊天。先对用户内容给予真诚的情感回应（如：That sounds great!），分享一点看法，最后自然地抛出一个追问。
    3. phase4_expansion: 提供 2 句针对阶段 3 的应答参考（1 基础，1 进阶）。
    请以 JSON 输出。
    """
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_text}],
            response_format={"type": "json_object"},
            temperature=0.7
        )
        return json.loads(response.choices[0].message.content)
    except: return None

# --- 6. 聊天区渲染 ---
st.title("🎙️ AI 英语口语教练")
if not groq_api_key:
    st.warning("👈 请先配置 API Key")
else:
    for i, msg in enumerate(st.session_state.messages):
        if msg["role"] == "user":
            with st.chat_message("user", avatar="👤"): st.write(msg["content"])
        else:
            with st.chat_message("assistant", avatar="🤖"):
                data = msg["content"]
                
                # --- 阶段 1: 纠错 ---
                st.markdown(f'<div class="phase-card phase-1"><div class="phase-header">🔵 AI 纠错点评</div>{data["phase1_correction"]}</div>', unsafe_allow_html=True)
                
                # --- 阶段 2: 优化表达 (手动播放) ---
                st.markdown(f'<div class="phase-card phase-2"><div class="phase-header">🟢 AI 优化表达 (点击跟读)</div><span style="font-size:1.2rem; color:#1B5E20;"><b>{data["phase2_optimized_text"]}</b></span>', unsafe_allow_html=True)
                # 生成优化句音频 (永不自动播放)
                opt_audio_b64 = asyncio.run(get_voice_audio(data["phase2_optimized_text"], v_map[voice_choice]))
                st.markdown(f'<audio src="data:audio/mp3;base64,{opt_audio_b64}" controls></audio></div>', unsafe_allow_html=True)
                
                # --- 阶段 3: 互动交流 (最新消息自动播放) ---
                st.markdown(f'<div class="phase-card phase-3"><div class="phase-header">💬 Chatting with Friend</div>{data["phase3_interaction"]}', unsafe_allow_html=True)
                
                # 判断是否为最新消息以决定是否自动播放
                current_interact_id = hash(data["phase3_interaction"])
                is_new_interact = (i == len(st.session_state.messages) - 1) and (st.session_state.last_played_id != current_interact_id)
                
                inter_audio_b64 = asyncio.run(get_voice_audio(data["phase3_interaction"], v_map[voice_choice]))
                autoplay_attr = "autoplay" if is_new_interact else ""
                st.markdown(f'<audio src="data:audio/mp3;base64,{inter_audio_b64}" {autoplay_attr} controls></audio></div>', unsafe_allow_html=True)
                
                # 记录已播放
                if is_new_interact: st.session_state.last_played_id = current_interact_id
                
                # --- 阶段 4: 回应参考 ---
                st.markdown(f"<div style='padding-left:15px; margin-bottom:15px;'><small style='color:#888;'>💡 回应参考: 1️⃣ {data['phase4_expansion'][0]} | 2️⃣ {data['phase4_expansion'][1]}</small></div>", unsafe_allow_html=True)

# --- 7. 底部输入 ---
st.markdown('<div class="footer-container">', unsafe_allow_html=True)
cols = st.columns([1, 6, 1])
with cols[1]:
    if input_mode == "语音":
        audio_in = mic_recorder(start_prompt="🎤 长按开始录音", stop_prompt="✅ 松开识别", key='recorder', use_container_width=True)
        if audio_in:
            curr_hash = hash(audio_in['bytes'])
            if "last_audio_hash" not in st.session_state or st.session_state.last_audio_hash != curr_hash:
                st.session_state.last_audio_hash = curr_hash
                with st.spinner("思考中..."):
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                        tmp.write(audio_in['bytes'])
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
        txt_in = st.chat_input("输入英语句子...")
        if txt_in:
            with st.spinner("思考中..."):
                ai_data = get_ai_response(txt_in)
                if ai_data:
                    st.session_state.messages.append({"role": "user", "content": txt_in})
                    st.session_state.messages.append({"role": "assistant", "content": ai_data})
                    st.rerun()
st.markdown('</div>', unsafe_allow_html=True)
