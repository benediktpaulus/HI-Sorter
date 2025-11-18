import logging
import os
import webview
from server import app  # Import the Flask app from server.py
from api import Api      # Import the Api class from api.py

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s'
)
logger = logging.getLogger("picture_sorter")
# Silence extremely noisy internal WebView2 messages that can flood the console
logging.getLogger('pywebview').setLevel(logging.CRITICAL)

# --- Main Entry Point ---
if __name__ == '__main__':
    # Workaround: WebView2 accessibility recursion on some Windows builds can
    # spam errors like AccessibilityObject.Bounds.Empty... Disable renderer accessibility.
    os.environ.setdefault('WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS', '--disable-renderer-accessibility')

    # Create an instance of our API class
    api = Api()
    logger.info("Starting Picture Sorter application")

    # Create the pywebview window
    try:
        window = webview.create_window(
            'Picture Sorter',
            app,        # The Flask app object to host
            js_api=api, # The Api class instance to expose to JavaScript
            width=1400,
            height=900,
        )
    except Exception as e:
        logger.exception("Failed to create webview window: %s", e)
        raise
    
    # After the window is created, give the api object a reference to it.
    # This allows the api.select_folder method to call window.create_file_dialog.
    api.window = window
    logger.info("Webview window created and API bound. Launching GUI...")

    # Start the application
    try:
        # Prefer Edge WebView2 backend on Windows. Disable debug for stability.
        webview.start(debug=False, gui='edgechromium')
    except Exception as e:
        logger.warning("Edge backend failed (%s). Falling back to default GUI backend.", e)
        # Fallback: let pywebview choose available backend (may be mshtml on Windows)
        webview.start(debug=False)