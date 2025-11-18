import os
import sys
from flask import Flask, render_template, send_file, request

def resource_path(rel):
    try:
        base = sys._MEIPASS  # set by PyInstaller
    except Exception:
        base = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base, rel)

app = Flask(
    __name__,
    template_folder=resource_path('templates'),
    static_folder=resource_path('static')
)

@app.route('/')
def index():
    """Serves the main HTML user interface."""
    return render_template('index.html')

@app.route('/image')
def get_image():
    """Serves the image file from the real path provided by the UI."""
    image_path = request.args.get('path')
    if image_path and os.path.exists(image_path):
        return send_file(image_path)
    return "Image not found", 404