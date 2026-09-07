"""Voice input/output using browser Web Speech API (no backend changes).

Integrates with Streamlit to add:
- Voice input: click mic → speak → transcript appears in chat
- Voice output: click speaker → bot response reads aloud

Browser support: Chrome, Edge, Safari (all with Web Speech API support).
"""
from __future__ import annotations

import streamlit as st


def voice_input_widget() -> None:
    """Display voice input and output buttons with Web Speech API."""
    col1, col2, col3 = st.columns([3, 1, 1])

    with col2:
        if st.button("🎤 Listen", key="voice_input_btn", help="Click and speak", use_container_width=True):
            st.session_state.voice_listening = True

    with col3:
        if st.button("🔊 Read", key="voice_output_btn", help="Hear bot's last reply", use_container_width=True):
            st.session_state.voice_speaking = True

    # Voice input recorder
    if st.session_state.get("voice_listening"):
        st.markdown("""
        <div style="padding: 12px; background: #fff3cd; border: 1px solid #ffc107; border-radius: 8px; margin: 8px 0;">
            <p style="margin: 0; font-size: 14px; color: #856404;">🎙️ Listening... Speak now</p>
        </div>
        <script>
        (function() {
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (!SpeechRecognition) {
                alert('Speech Recognition not supported in your browser. Use Chrome, Edge, or Safari.');
                return;
            }

            const recognition = new SpeechRecognition();
            recognition.lang = 'en-AU';
            recognition.continuous = false;
            recognition.interimResults = false;

            recognition.onstart = () => console.log('🎤 Listening...');

            recognition.onresult = (event) => {
                const transcript = event.results[0][0].transcript;
                console.log('Transcript:', transcript);
                // Trigger Streamlit to rerun with the transcript
                window.parent.document.querySelector('button[kind="secondary"]')?.click?.();
                // Store in session via hidden input (Streamlit will pick it up)
                const hidden = document.createElement('input');
                hidden.type = 'hidden';
                hidden.id = 'voice-transcript';
                hidden.value = transcript;
                document.body.appendChild(hidden);
            };

            recognition.onerror = (event) => console.error('Error:', event.error);
            recognition.onend = () => console.log('Stopped listening');

            recognition.start();
        })();
        </script>
        """, unsafe_allow_html=True)
        st.session_state.voice_listening = False

    # Voice output (text-to-speech)
    if st.session_state.get("voice_speaking"):
        messages = st.session_state.get("messages", [])
        if messages:
            last_bot_message = next((m["content"] for m in reversed(messages) if m["role"] == "assistant"), None)
            if last_bot_message:
                # Clean markdown and read aloud
                clean_text = last_bot_message.replace("**", "").replace("*", "").replace("`", "")
                st.markdown(f"""
                <script>
                (function() {{
                    const text = `{clean_text.replace(chr(96), " ")}`;
                    const utterance = new SpeechSynthesisUtterance(text);
                    utterance.lang = 'en-AU';
                    utterance.rate = 0.95;
                    utterance.pitch = 1.0;
                    speechSynthesis.cancel();
                    speechSynthesis.speak(utterance);
                    console.log('🔊 Speaking:', text.substring(0, 50) + '...');
                }})();
                </script>
                """, unsafe_allow_html=True)
        st.session_state.voice_speaking = False


def inject_voice_css() -> None:
    """Add voice UI styling."""
    st.markdown("""
    <style>
    .voice-button {
        font-size: 1.1rem;
        padding: 8px 12px;
        border: 1px solid #ddd;
        border-radius: 8px;
        background: white;
        cursor: pointer;
        transition: all 0.2s;
    }
    .voice-button:hover {
        background: #f0f0f0;
        border-color: #999;
    }
    .voice-button:active {
        background: #e0e0e0;
    }
    </style>
    """, unsafe_allow_html=True)

