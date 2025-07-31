from flask import Flask, request, render_template, send_file, jsonify
import yt_dlp
from yt_dlp.utils import DownloadError
import os, ssl, threading, time, atexit, shutil, subprocess
from datetime import datetime, timedelta

app = Flask(__name__)
ssl._create_default_https_context = ssl._create_unverified_context

download_progress = {"percentage": 0, "status": "", "error": "", "filename": ""}
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def cleanup_downloads():
    while True:
        try:
            now = datetime.now()
            for f in os.listdir(DOWNLOAD_DIR):
                path = os.path.join(DOWNLOAD_DIR, f)
                if now - datetime.fromtimestamp(os.path.getmtime(path)) > timedelta(hours=1):
                    os.remove(path)
        except:
            pass
        time.sleep(3600)
threading.Thread(target=cleanup_downloads, daemon=True).start()
atexit.register(lambda: shutil.rmtree(DOWNLOAD_DIR, ignore_errors=True))

def download_progress_hook(d):
    global download_progress
    if d['status'] == 'downloading':
        try:
            download_progress['percentage'] = float(d.get('_percent_str', '0%').strip('%'))
        except:
            pass
        download_progress['status'] = 'Downloading'
    elif d['status'] == 'finished':
        download_progress.update({
            'percentage': 100,
            'status': 'Downloaded',
            'filename': d.get('info_dict', {}).get('title', 'output') + f".{d.get('ext', 'mp4')}"
        })
    elif d['status'] == 'error':
        download_progress['error'] = 'Download failed'

def check_ffmpeg():
    return os.path.isfile('./ffmpeg') and os.access('./ffmpeg', os.X_OK)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    global download_progress
    download_progress = {"percentage": 0, "status": "", "error": "", "filename": ""}

    url = request.form.get('url')
    fmt = request.form.get('format', 'mp4')
    resolution = request.form.get('resolution', '720').replace('p', '')

    if not url:
        download_progress['error'] = 'No URL provided'
        return jsonify(download_progress)
    if not os.path.exists('cookies.txt'):
        download_progress['error'] = 'cookies.txt file not found'
        return jsonify(download_progress)
    if fmt == 'mp4' and not check_ffmpeg():
        download_progress['error'] = 'FFmpeg not available'
        return jsonify(download_progress)

    output_file = os.path.join(DOWNLOAD_DIR, f"output_{int(time.time())}.{fmt}")
    for f in os.listdir(DOWNLOAD_DIR):
        if f.endswith(f".{fmt}"):
            os.remove(os.path.join(DOWNLOAD_DIR, f))

    ffmpeg_path = os.path.abspath('./ffmpeg')

    base_opts = {
        'outtmpl': output_file,
        'noplaylist': True,
        'progress_hooks': [download_progress_hook],
        'cookiefile': 'cookies.txt',
        'verbose': True,
        'ffmpeg_location': ffmpeg_path
    }

    if fmt == 'mp4':
        opts_video = {**base_opts, **{
            'format': f'bestvideo[height<={resolution}][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'merge_output_format': 'mp4'
        }}
    else:
        opts_video = {**base_opts, **{
            'format': 'bestaudio[ext=m4a]/bestaudio',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        }}

    def download_thread():
        try:
            with yt_dlp.YoutubeDL(opts_video) as ydl:
                ydl.download([url])
        except DownloadError as e:
            print(f"Primary download failed: {e}")
            if fmt == 'mp4':
                # fallback to MP3
                fallback_file = output_file.replace('.mp4', '.mp3')
                opts_audio = {**base_opts, **{
                    'outtmpl': fallback_file,
                    'format': 'bestaudio[ext=m4a]/bestaudio',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }]
                }}
                try:
                    with yt_dlp.YoutubeDL(opts_audio) as ydl2:
                        ydl2.download([url])
                    download_progress['status'] = 'Downloaded'
                    download_progress['filename'] = os.path.basename(fallback_file)
                    print("Fallback audio-only succeeded")
                except DownloadError as e2:
                    download_progress['error'] = f"Audio fallback failed: {e2}"
                    print(f"Fallback download error: {e2}")
            else:
                download_progress['error'] = f"Download failed: {e}"

    threading.Thread(target=download_thread, daemon=True).start()
    return jsonify({"status": "started"})

@app.route('/progress')
def progress():
    return jsonify(download_progress)

@app.route('/download_file')
def download_file():
    if download_progress.get('status') == 'Downloaded':
        fmt = request.args.get('format', 'mp4')
        for f in os.listdir(DOWNLOAD_DIR):
            if f.endswith(f".{fmt}"):
                path = os.path.join(DOWNLOAD_DIR, f)
                return send_file(path, as_attachment=True, download_name=download_progress.get('filename'))
        return jsonify({"error": "File not found"}), 404
    return jsonify({"error": "Download not complete"}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
