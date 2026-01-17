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
st.set_page_config(page_title="AI 多语种口语私教", layout="wide", initial_sidebar_state="collapsed")

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
        audio { height: 35px; width: 100%; margin-top: 10px; }
    </style>
""", unsafe_allow_html=True)

# --- 3. 状态初始化 ---
groq_api_key = st.secrets.get("GROQ_API_KEY", "")
if "messages" not in st.session_state: st.session_state.messages = []
if "last_played_id" not in st.session_state: st.session_state.last_played_id = None

# --- 4. 侧边栏配置 ---
with st.sidebar:
    st.title("💡 教练设置")
    if not groq_api_key:
        groq_api_key = st.text_input("请输入 Groq API Key", type="password")
    
    # 新增：目标语言选择
    target_lang = st.selectbox("目标学习语言", ["英语 (English)", "日语 (日本語)", "韩语 (한국어)", "德语 (Deutsch)", "法语 (Français)"])
    lang_code = target_lang.split(" (")[0]
    
    # 动态匹配 TTS 声音
    voice_options = {
        "英语": {"Ava (美)": "en-US-AvaMultilingualNeural", "Andrew (美)": "en-US-AndrewMultilingualNeural", "Sonia (英)": "en-GB-SoniaNeural"},
        "日语": {"Nanami": "ja-JP-NanamiNeural", "Keita": "ja-JP-KeitaNeural"},
        "韩语": {"Sun-Hi": "ko-KR-SunHiNeural", "In-Joon": "ko-KR-InJoonNeural"},
        "德语": {"Katja": "de-DE-KatjaNeural", "Killian": "de-DE-KillianNeural"},
        "法语": {"Denise": "fr-FR-DeniseNeural", "Eloise": "fr-FR-EloiseNeural"}
    }
    current_voices = voice_options.get(lang_code, voice_options["英语"])
    voice_name = st.selectbox("教练声音", list(current_voices.keys()))
    selected_voice = current_voices[voice_name]

    input_mode = st.radio("录入模式", ["语音", "文字"])
    if st.button("🗑️ 清空历史"):
        st.session_state.messages = []
        st.session_state.last_played_id = None
        st.rerun()

groq_client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=groq_api_key) if groq_api_key else None

# --- 5. 核心辅助功能 ---
async def get_voice_audio(text, voice):
    if not text or len(text.strip()) == 0: return ""
    try:
        communicate = edge_tts.Communicate(text, voice)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            tmp_path = tmp.name
        await communicate.save(tmp_path)
        with open(tmp_path, "rb") as f: data = f.read()
        os.remove(tmp_path)
        return base64.b64encode(data).decode()
    except: return ""

def get_ai_response(user_text, target_language):
    system_prompt = f"""
    你现在是一名精通中英双语的专业口语教练，目前正在教用户学习【{target_language}】。
    请严格按顺序执行并输出 JSON：
    1. 【身份：专业导师】
       - phase1_correction: 针对用户的【{target_language}】文本进行纠错和发音/语调指导（始终用中文回答）。
       - phase2_optimized_text: 提供一个最地道、完整的优化例句（必须仅使用【{target_language}】）。
    2. 【身份：知心朋友】
       - phase3_interaction: 请用所在语言的国家居民的正常状态（该内敛就内敛，该热情就热情），对用户内容给予真诚的回应，分享看法，最后追问（必须始终使用【{target_language}】）。
    3. phase4_expansion: 提供 2 句针对阶段 3 的应答参考（必须是列表格式，且仅使用【{target_language}】）。
    
    注意：除了 phase1 用中文外，其余所有教学和互动内容必须严格使用【{target_language}】，严禁切换语言。
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
st.title(f"🎙️ AI {lang_code}口语私教")

if not groq_api_key:
    st.warning("👈 请先在左侧配置 API Key")
else:
    for i, msg in enumerate(st.session_state.messages):
        if msg["role"] == "user":
            with st.chat_message("user", avatar="👤"): st.write(msg["content"])
        else:
            with st.chat_message("assistant", avatar="🤖"):
                data = msg["content"]
                p1 = data.get("phase1_correction") or data.get("correction") or "AI 暂无点评"
                st.markdown(f'<div class="phase-card phase-1"><div class="phase-header">🔵 AI 纠错点评 (中文)</div>{p1}</div>', unsafe_allow_html=True)
                
                p2 = data.get("phase2_optimized_text") or ""
                if p2:
                    st.markdown(f'<div class="phase-card phase-2"><div class="phase-header">🟢 优化表达 (点击跟读)</div><span style="font-size:1.2rem; color:#1B5E20;"><b>{p2}</b></span>', unsafe_allow_html=True)
                    opt_audio = asyncio.run(get_voice_audio(p2, selected_voice))
                    if opt_audio: st.markdown(f'<audio src="data:audio/mp3;base64,{opt_audio}" controls></audio></div>', unsafe_allow_html=True)
                    else: st.markdown('</div>', unsafe_allow_html=True)

                p3 = data.get("phase3_interaction") or ""
                st.markdown(f'<div class="phase-card phase-3"><div class="phase-header">💬 互动交流</div>{p3}', unsafe_allow_html=True)
                inter_audio = asyncio.run(get_voice_audio(p3, selected_voice))
                if inter_audio:
                    curr_id = hash(p3)
                    is_new = (i == len(st.session_state.messages) - 1) and (st.session_state.last_played_id != curr_id)
                    autoplay = "autoplay" if is_new else ""
                    st.markdown(f'<audio src="data:audio/mp3;base64,{inter_audio}" {autoplay} controls></audio></div>', unsafe_allow_html=True)
                    if is_new: st.session_state.last_played_id = curr_id
                else: st.markdown('</div>', unsafe_allow_html=True)

                p4 = data.get("phase4_expansion", [])
                if isinstance(p4, list) and len(p4) > 0:
                    tips = " | ".join([f"{idx+1}️⃣ {text}" for idx, text in enumerate(p4)])
                    st.markdown(f"<div style='padding-left:15px; margin-bottom:15px;'><small style='color:#888;'>💡 回应参考: {tips}</small></div>", unsafe_allow_html=True)

# --- 7. 底部输入与校验 ---
st.markdown('<div class="footer-container">', unsafe_allow_html=True)
cols = st.columns([1, 6, 1])
with cols[1]:
    if input_mode == "语音":
        audio_in = mic_recorder(start_prompt="🎤 长按录音", stop_prompt="✅ 松开发送", key='recorder', use_container_width=True)
        if audio_in:
            # 校验1：检查字节大小（例如小于 1000 字节通常是误触）
            if len(audio_in['bytes']) < 1500:
                st.warning("⚠️ 录音时间过短，请长按录制完整的句子。")
            else:
                curr_hash = hash(audio_in['bytes'])
                if "last_audio_hash" not in st.session_state or st.session_state.last_audio_hash != curr_hash:
                    st.session_state.last_audio_hash = curr_hash
                    with st.spinner("正在识别语音..."):
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                            tmp.write(audio_in['bytes'])
                            t_path = tmp.name
                        with open(t_path, "rb") as f:
                            transcript = groq_client.audio.transcriptions.create(model="whisper-large-v3", file=f)
                        os.remove(t_path)
                        u_text = transcript.text
                        # 校验2：检查识别出的文本是否有效
                        if not u_text or len(u_text.strip()) < 2:
                            st.warning("⚠️ 无法识别您的语音，请重试。")
                        else:
                            ai_data = get_ai_response(u_text, lang_code)
                            if ai_data:
                                st.session_state.messages.append({"role": "user", "content": u_text})
                                st.session_state.messages.append({"role": "assistant", "content": ai_data})
                                st.rerun()
    else:
        txt_in = st.chat_input(f"用{lang_code}输入句子...")
        if txt_in:
            ai_data = get_ai_response(txt_in, lang_code)
            if ai_data:
                st.session_state.messages.append({"role": "user", "content": txt_in})
                st.session_state.messages.append({"role": "assistant", "content": ai_data})
                st.rerun()
st.markdown('</div>', unsafe_allow_html=True)


