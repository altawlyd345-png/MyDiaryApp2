"""Launcher: catches startup errors and shows them instead of a blank white screen."""
import traceback
import crashguard
crashguard.install()
try:
    import receiver_app          # runs the app on import
except Exception:
    crashguard.show_error("Receiver - خطأ عند التشغيل", traceback.format_exc())
