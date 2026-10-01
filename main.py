from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp
import os

app = Flask(__name__)
CORS(app)

def find_cookie_file():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for fname in ['cookies.txt', 'cookie.txt', 'youtube_cookies.txt']:
        p = os.path.join(base_dir, fname)
        if os.path.exists(p):
            return p
    try:
        for f in os.listdir(base_dir):
            if f.endswith('.txt') and f != 'requirements.txt':
                return os.path.join(base_dir, f)
    except Exception:
        pass
    return None

def extract_with_fallbacks(url):
    cookie_file = find_cookie_file()
    # ইউটিউবের বিভিন্ন ক্লায়েন্ট দিয়ে একের পর এক চেষ্টা করার তালিকা
    client_configs = [
        ['web_safari', 'web_embedded'],
        ['ios', 'android'],
        ['mweb', 'android'],
        ['android_creator'],
        None
    ]
    
    last_error = None
    for clients in client_configs:
        opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
                'Accept-Language': 'en-US,en;q=0.9',
            }
        }
        if cookie_file:
            opts['cookiefile'] = cookie_file
        if clients:
            opts['extractor_args'] = {'youtube': {'player_client': clients}}
        
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception as e:
            last_error = str(e)
            continue
            
    raise Exception(last_error or "Could not extract video info")

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "online",
        "message": "VideoDrop Backend Microservice is running perfectly!",
        "cookies_detected": bool(find_cookie_file())
    })

@app.route('/debug', methods=['GET'])
def debug():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        files = os.listdir(base_dir)
    except Exception as e:
        files = [str(e)]
    cookie_file = find_cookie_file()
    return jsonify({
        "files_in_app": files,
        "cookie_file_found": cookie_file
    })

@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.get_json() or {}
    url = data.get('url')
    if not url:
        return jsonify({"error": "URL is required"}), 400

    try:
        info = extract_with_fallbacks(url)
        
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
                    "quality": f"{height}p",
                    "format": ext,
                    "size": size_str,
                    "downloadAvailable": True,
                    "downloadUrl": stream_url
                })
        
        # অডিও অপশন (MP3 / Audio)
        formats.append({
            "id": "audio",
            "quality": "Audio Only",
            "format": "mp3",
            "size": "Audio Stream",
            "downloadAvailable": True,
            "downloadUrl": info.get('url') or url
        })

        duration_sec = info.get('duration', 0)
        mins = int(duration_sec // 60)
        secs = int(duration_sec % 60)
        duration_str = f"{mins:02d}:{secs:02d}" if duration_sec else None

        return jsonify({
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
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json() or {}
    url = data.get('url')
    format_id = data.get('formatId', '')
    
    try:
        info = extract_with_fallbacks(url)
        
        for f in info.get('formats', []):
            if format_id.replace('p', '') == str(f.get('height')) and f.get('url'):
                return jsonify({
                    "downloadUrl": f.get('url'),
                    "filename": f"{info.get('title', 'video')}.mp4"
                })
        
        return jsonify({
            "downloadUrl": info.get('url'),
            "filename": f"{info.get('title', 'video')}.mp4"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
