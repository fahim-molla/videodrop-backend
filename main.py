from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp
import os
import time

app = Flask(__name__)
CORS(app)

# ফাস্ট ক্যাশিং ডিকশনারি (যাতে একই লিংকে বারবার সময় নষ্ট না হয়)
URL_CACHE = {}
CACHE_TTL = 300 # ৫ মিনিট ক্যাশ থাকবে

def get_cached(url):
    item = URL_CACHE.get(url)
    if item and time.time() - item['time'] < CACHE_TTL:
        return item['data']
    return None

def set_cached(url, data):
    URL_CACHE[url] = {'data': data, 'time': time.time()}

def get_ydl_options(platform='generic'):
    opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'socket_timeout': 6,
    }
    # ইউটিউবের ক্ষেত্রে অ্যান্ড্রয়েড ক্লায়েন্ট ব্যবহার করা হয় যা বট চেক বাইপাস করে
    if 'youtube' in platform or 'youtu.be' in platform:
        opts['extractor_args'] = {'youtube': {'player_client': ['android']}}
        opts['http_headers'] = {
            'User-Agent': 'com.google.android.youtube/19.05.36 (Linux; U; Android 14; US) gzip'
        }
    return opts

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "online",
        "service": "VideoDrop Ultra-Fast Multi-Platform Downloader",
        "supported": ["YouTube", "Facebook", "Instagram", "TikTok"]
    })

@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.get_json() or {}
    url = data.get('url')
    if not url:
        return jsonify({"error": "URL is required"}), 400

    # ক্যাশ চেক
    cached = get_cached(url)
    if cached:
        return jsonify(cached)

    try:
        ydl_opts = get_ydl_options(url)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            formats = []
            seen_heights = set()
            
            # ভিডিও ফরম্যাট ফিল্টারিং
            for f in info.get('formats', []):
                height = f.get('height')
                ext = f.get('ext', 'mp4')
                stream_url = f.get('url')
                
                if height and height in [1080, 720, 480, 360] and height not in seen_heights and stream_url:
                    seen_heights.add(height)
                    filesize = f.get('filesize') or f.get('filesize_approx')
                    size_str = f"{round(filesize / (1024*1024), 1)} MB" if filesize else "Fast Stream"
                    
                    formats.append({
                        "id": f"{height}p",
                        "quality": f"{height}p {'Full HD' if height >= 1080 else 'HD' if height >= 720 else 'SD'}",
                        "format": ext,
                        "size": size_str,
                        "downloadAvailable": True,
                        "downloadUrl": stream_url
                    })
            
            # যদি সরাসরি হাইট না পাওয়া যায় (যেমন ফেসবুক/ইনস্টাগ্রাম/টিকটক)
            if not formats:
                formats.append({
                    "id": "hd",
                    "quality": "HD Quality (Source)",
                    "format": "mp4",
                    "size": "Original Stream",
                    "downloadAvailable": True,
                    "downloadUrl": info.get('url')
                })
            
            # অডিও (MP3) অপশন
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
        ydl_opts = get_ydl_options(url)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
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
