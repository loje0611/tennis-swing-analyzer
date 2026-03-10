import streamlit as st
import streamlit.components.v1 as components

from src.settings_persistence import get_settings, save_settings


def _on_tts_toggle():
    """Persist TTS toggle to settings.json and keep session state in sync."""
    new_value = st.session_state.get("tts_toggle_key", False)
    save_settings(tts_enabled=new_value)
    st.session_state.tts_enabled = new_value


def render_tts_audio_toggle():
    """Render TTS on/off toggle; value persisted to settings.json across restarts."""
    current = st.session_state.get("tts_enabled", get_settings().get("tts_enabled", False))
    st.toggle(
        "🔊 오디오",
        value=current,
        key="tts_toggle_key",
        on_change=_on_tts_toggle,
    )
    # One-time unlock for mobile when turning on (user gesture = toggle click)
    if current and not st.session_state.get("tts_unlock_done"):
        components.html("""
        <script>
            var u = new SpeechSynthesisUtterance('');
            u.volume = 0; u.lang = 'ko-KR';
            window.speechSynthesis.speak(u);
        </script>
        """, height=0)
        st.session_state.tts_unlock_done = True


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
