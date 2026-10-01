from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp
import os
import time

app = Flask(__name__)
CORS(app)

URL_CACHE = {}
CACHE_TTL = 300  # ৫ মিনিট ক্যাশ

def get_cached(url):
    item = URL_CACHE.get(url)
    if item and time.time() - item['time'] < CACHE_TTL:
        return item['data']
    return None

def set_cached(url, data):
    URL_CACHE[url] = {'data': data, 'time': time.time()}

def find_cookie_file():
    paths = [
        '/app/cookies.txt',
        'cookies.txt',
        os.path.join(os.getcwd(), 'cookies.txt'),
        '/tmp/cookies.txt'
    ]
    for p in paths:
        if os.path.exists(p) and os.path.getsize(p) > 20:
            return p
    return None

def extract_media_info(url):
    is_yt = 'youtube.com' in url or 'youtu.be' in url
    cookie_file = find_cookie_file()

    attempts = []
    if is_yt:
        if cookie_file:
            # কুকিজ থাকলে কুকিজ ফাইল দিয়ে অথেন্টিকেশন (ইউটিউবের জন্য সেরা উপায়)
            attempts.append({'cookiefile': cookie_file})
        # ফলব্যাক হিসেবে মোবাইল ও আইওএস ক্লায়েন্ট
        attempts.append({'extractor_args': {'youtube': {'player_client': ['ios']}}})
        attempts.append({'extractor_args': {'youtube': {'player_client': ['mweb']}}})
        attempts.append({'extractor_args': {'youtube': {'player_client': ['android']}}})
        attempts.append({})
    else:
        # ফেসবুক, টিকটক বা ইনস্টাগ্রাম সরাসরি কাজ করে
        attempts.append({})

    last_err = None
    for extra in attempts:
        opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'socket_timeout': 10,
        }
        opts.update(extra)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception as e:
            last_err = str(e)
            continue

    raise Exception(last_err or "Media extraction failed")

@app.route('/', methods=['GET'])
def home():
    cookie_found = find_cookie_file()
    return jsonify({
        "status": "online",
        "service": "VideoDrop Ultra Engine",
        "cookies_detected": bool(cookie_found),
        "supported": ["YouTube", "Facebook", "Instagram", "TikTok"]
    })

@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.get_json() or {}
    url = data.get('url')
    if not url:
        return jsonify({"error": "URL is required"}), 400

    cached = get_cached(url)
    if cached:
        return jsonify(cached)

    try:
        info = extract_media_info(url)
        formats = []
        seen_heights = set()

        for f in info.get('formats', []):
            height = f.get('height')
            ext = f.get('ext', 'mp4')
            stream_url = f.get('url')

            if height and height in [1080, 720, 480, 360] and height not in seen_heights and stream_url:
                seen_heights.add(height)
                filesize = f.get('filesize') or f.get('filesize_approx')
                size_str = f"{round(filesize / (1024*1024), 1)} MB" if filesize else "Direct Stream"

                formats.append({
                    "id": f"{height}p",
                    "quality": f"{height}p {'Full HD' if height >= 1080 else 'HD' if height >= 720 else 'SD'}",
                    "format": ext,
                    "size": size_str,
                    "downloadAvailable": True,
                    "downloadUrl": stream_url
                })

        if not formats:
            formats.append({
                "id": "hd",
                "quality": "HD Quality (Source)",
                "format": "mp4",
                "size": "Original Stream",
                "downloadAvailable": True,
                "downloadUrl": info.get('url')
            })

        # অডিও ফরম্যাট (MP3)
        audio_url = None
        for f in info.get('formats', []):
            if f.get('acodec') != 'none' and f.get('vcodec') == 'none' and f.get('url'):
                audio_url = f.get('url')
                break

        formats.append({
            "id": "audio",
            "quality": "Audio Only (MP3)",
            "format": "mp3",
            "size": "Audio Stream",
            "downloadAvailable": True,
            "downloadUrl": audio_url or info.get('url')
        })

        duration_sec = info.get('duration', 0)
        mins = int(duration_sec // 60)
        secs = int(duration_sec % 60)
        duration_str = f"{mins:02d}:{secs:02d}" if duration_sec else None

        res_data = {
            "success": True,
            "title": info.get('title', 'Video'),
            "thumbnail": info.get('thumbnail', ''),
            "duration": duration_str,
            "author": {
                "name": info.get('uploader') or info.get('channel') or 'Creator',
                "url": info.get('uploader_url')
            },
            "downloadConfigured": True,
            "formats": formats
        }

        set_cached(url, res_data)
        return jsonify(res_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json() or {}
    url = data.get('url')
    format_id = data.get('formatId', '720p')

    if not url:
        return jsonify({"error": "URL is required"}), 400

    try:
        info = extract_media_info(url)
        chosen_url = None

        if format_id == 'audio':
            for f in info.get('formats', []):
                if f.get('acodec') != 'none' and f.get('vcodec') == 'none' and f.get('url'):
                    chosen_url = f.get('url')
                    break
        else:
            height_num = int(format_id.replace('p', '')) if format_id.replace('p', '').isdigit() else None
            if height_num:
                for f in info.get('formats', []):
                    if f.get('height') == height_num and f.get('url'):
                        chosen_url = f.get('url')
                        break

        if not chosen_url:
            for f in reversed(info.get('formats', [])):
                if f.get('url') and str(f.get('url')).startswith('http'):
                    chosen_url = f.get('url')
                    break

        title = info.get('title', 'video')
        clean_title = "".join(c for c in title if c.isalnum() or c in (' ', '_', '-')).strip()
        ext = 'mp3' if format_id == 'audio' else 'mp4'

        return jsonify({
            "downloadUrl": chosen_url or info.get('url'),
            "filename": f"{clean_title}.{ext}"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
