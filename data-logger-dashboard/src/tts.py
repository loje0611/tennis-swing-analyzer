import streamlit as st
import streamlit.components.v1 as components


def render_tts_audio_button():
    """Render '🔊 오디오 켜기' button to unlock mobile browser audio policy.
    
    Mobile browsers require a user gesture before speechSynthesis can speak.
    This button performs a silent speak() call to unlock the audio context,
    then sets tts_enabled=True so future TTS calls work automatically.
    """
    if st.session_state.get('tts_enabled', False):
        st.success("🔊 오디오 활성화됨")
        return

    if st.button("🔊 오디오 켜기", type="primary", use_container_width=True):
        # Inject silent speech to unlock mobile audio policy
        components.html("""
        <script>
            const unlockUtter = new SpeechSynthesisUtterance('');
            unlockUtter.volume = 0;
            unlockUtter.lang = 'ko-KR';
            window.speechSynthesis.speak(unlockUtter);
        </script>
        """, height=0)
        st.session_state.tts_enabled = True
        st.rerun()


def render_tts_speaker(message, swing_id):
    """Inject a speechSynthesis call into the browser if there's a new swing.
    
    Uses swing_id to prevent duplicate announcements. The JS checks whether
    the current swing_id differs from the last spoken one before speaking.
    
    Args:
        message: Korean text to speak (e.g. "포핸드, 110 킬로미터")
        swing_id: Unique identifier for the current swing event
    """
    if not message or not swing_id:
        return

    # Escape quotes in message for safe JS injection
    safe_message = message.replace("'", "\\'").replace('"', '\\"')

    components.html(f"""
    <script>
    (function() {{
        var swingId = "{swing_id}";
        var message = "{safe_message}";

        // Check localStorage to prevent duplicate speech across reruns
        var lastSpoken = window.localStorage.getItem('tts_last_spoken_id') || '';

        if (swingId !== lastSpoken) {{
            window.localStorage.setItem('tts_last_spoken_id', swingId);

            // Cancel any ongoing speech
            window.speechSynthesis.cancel();

            var utter = new SpeechSynthesisUtterance(message);
            utter.lang = 'ko-KR';
            utter.rate = 1.1;
            utter.pitch = 1.0;
            utter.volume = 1.0;
            window.speechSynthesis.speak(utter);
        }}
    }})();
    </script>
    """, height=0)
