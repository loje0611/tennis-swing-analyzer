import streamlit as st
import streamlit.components.v1 as components
import time
import json

from src.settings_persistence import get_settings, save_settings

# localStorage key used by fragment (write) and listener (read)
TTS_REQUEST_KEY = "tts_request"


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
    if current and not st.session_state.get("tts_unlock_done"):
        components.html("""
        <script>
            var u = new SpeechSynthesisUtterance('');
            u.volume = 0; u.lang = 'en-US';
            window.speechSynthesis.speak(u);
        </script>
        """, height=0)
        st.session_state.tts_unlock_done = True


def render_tts_listener():
    """Persistent TTS listener: rendered once in the main script (not in fragment).
    Polls localStorage for 'tts_request'; speaks when swing_id changes. Survives
    fragment re-renders so 'Next' is not lost when the fragment output is replaced.
    """
    components.html("""
    <script>
    (function() {
        var LAST_ID_KEY = 'tts_last_spoken_id';
        function poll() {
            try {
                var raw = localStorage.getItem('tts_request');
                if (!raw) return;
                var o = JSON.parse(raw);
                var lastSpokenId = localStorage.getItem(LAST_ID_KEY) || '';
                if (o && o.swing_id && o.swing_id !== lastSpokenId) {
                    localStorage.setItem(LAST_ID_KEY, o.swing_id);
                    if (window.speechSynthesis) {
                        window.speechSynthesis.cancel();
                        var u = new SpeechSynthesisUtterance(o.message || '');
                        u.lang = 'en-US';
                        u.rate = 1.1;
                        u.volume = 1.0;
                        window.speechSynthesis.speak(u);
                    }
                }
            } catch (e) {}
        }
        setInterval(poll, 150);
    })();
    </script>
    """, height=0)


def render_tts_request_write(tts_enabled, tts_message, tts_swing_id):
    """Fragment-only: write current TTS request to localStorage. The persistent
    listener (render_tts_listener) in the main script will pick it up and speak.
    Does not perform speech in this iframe, so 0.2s replacement does not kill 'Next'.
    """
    if not tts_enabled or not tts_message or not tts_swing_id:
        components.html(f"<!-- tts-write-noop {time.time()} -->", height=0)
        return
    payload = {"swing_id": tts_swing_id, "message": tts_message}
    json_str = json.dumps(payload, ensure_ascii=False)
    # Escape for embedding inside a JS string
    escaped = (
        json_str.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("</script>", "<\\/script>")
    )
    components.html(f"""
    <script>
    (function() {{
        try {{
            localStorage.setItem("{TTS_REQUEST_KEY}", "{escaped}");
        }} catch (e) {{}}
    }})();
    </script>
    """, height=0)
