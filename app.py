from flask import Flask, request, render_template, send_file, jsonify
import yt_dlp
import os
import ssl
import threading
import time
import atexit
import shutil
from datetime import datetime, timedelta
import subprocess

app = Flask(__name__)

ssl._create_default_https_context = ssl._create_unverified_context

# Global variables for progress tracking
download_progress = {"percentage": 0, "status": "", "error": "", "filename": ""}

# Directory for temporary files
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Clean up old files (older than 1 hour)
def cleanup_downloads():
    while True:
        try:
            now = datetime.now()
            for filename in os.listdir(DOWNLOAD_DIR):
                file_path = os.path.join(DOWNLOAD_DIR, filename)
                file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                if now - file_mtime > timedelta(hours=1):
                    os.remove(file_path)
        except Exception:
            pass
        time.sleep(3600)  # Check every hour

# Start cleanup thread
threading.Thread(target=cleanup_downloads, daemon=True).start()

# Clean up downloads folder on exit
def remove_downloads():
    shutil.rmtree(DOWNLOAD_DIR, ignore_errors=True)

atexit.register(remove_downloads)

def download_progress_hook(d):
    global download_progress
    if d['status'] == 'downloading':
        progress = d.get('_percent_str', '0%').replace('%', '')
        try:
            download_progress['percentage'] = float(progress)
        except ValueError:
            pass
        download_progress['status'] = 'Downloading'
    elif d['status'] == 'finished':
        download_progress['percentage'] = 100
        download_progress['status'] = 'Downloaded'
        download_progress['filename'] = d.get('info_dict', {}).get('title', 'output') + f".{d.get('ext', 'mp4')}"
    elif d['status'] == 'error':
        download_progress['error'] = 'Download failed'

def check_ffmpeg():
    try:
        result = subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
        print(f"FFmpeg version: {result.stdout.splitlines()[0]}")  # Debug FFmpeg version
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"FFmpeg check failed: {str(e)}")  # Debug FFmpeg error
        return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    global download_progress
    download_progress = {"percentage": 0, "status": "", "error": "", "filename": ""}
    
    url = request.form.get('url')
    format_type = request.form.get('format', 'mp4')
    resolution = request.form.get('resolution', '720').replace('p', '')

    print(f"Starting download: URL={url}, Format={format_type}, Resolution={resolution}")  # Debug log

    if not url:
        download_progress['error'] = 'No URL provided'
        print("Error: No URL provided")  # Debug log
        return jsonify(download_progress)

    if format_type == 'mp4' and not check_ffmpeg():
        download_progress['error'] = 'FFmpeg is not installed. Please install FFmpeg to download videos.'
        print("Error: FFmpeg not installed")  # Debug log
        return jsonify(download_progress)

    output_file = os.path.join(DOWNLOAD_DIR, f"output_{int(time.time())}.{format_type}")
    
    # Remove any existing files with same extension
    for f in os.listdir(DOWNLOAD_DIR):
        if f.endswith(f".{format_type}"):
            os.remove(os.path.join(DOWNLOAD_DIR, f))
            print(f"Removed existing file: {f}")  # Debug log

    if format_type == 'mp4':
        options = {
            'outtmpl': output_file,
            'noplaylist': True,
            'progress_hooks': [download_progress_hook],
            'format': f'bestvideo[height<={resolution}][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'merge_output_format': 'mp4',
            'ffmpeg_location': 'ffmpeg',  # Use ffmpeg from PATH on Linux/Render
            'verbose': True,
        }
    else:  # mp3 extraction
        options = {
            'outtmpl': output_file,
            'noplaylist': True,
            'progress_hooks': [download_progress_hook],
            'format': 'bestaudio[ext=m4a]/bestaudio',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'ffmpeg_location': 'ffmpeg',  # Use ffmpeg from PATH
            'verbose': True,
        }

    def download_thread():
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([url])
            print("Download completed successfully")  # Debug log
        except Exception as e:
            download_progress['error'] = f"Download failed: {str(e)}"
            print(f"Download error: {str(e)}")  # Debug log

    threading.Thread(target=download_thread, daemon=True).start()
    return jsonify({"status": "started"})

@app.route('/progress')
def progress():
    global download_progress
    return jsonify(download_progress)

@app.route('/download_file')
def download_file():
    global download_progress
    if download_progress.get('status') == 'Downloaded':
        format_type = request.args.get('format', 'mp4')
        for f in os.listdir(DOWNLOAD_DIR):
            if f.endswith(f".{format_type}"):
                file_path = os.path.join(DOWNLOAD_DIR, f)
                filename = download_progress.get('filename', f"output.{format_type}")
                print(f"Serving file: {file_path} as {filename}")  # Debug log
                return send_file(file_path, as_attachment=True, download_name=filename)
        download_progress['error'] = "File not found"
        print("Error: File not found in downloads directory")  # Debug log
        return jsonify({"error": "File not found"}), 404
    download_progress['error'] = "Download not complete"
    print("Error: Download not complete")  # Debug log
    return jsonify({"error": "Download not complete"}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
