from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import os

app = FastAPI(title="VideoDrop Microservice")

# সব ধরনের রিকোয়েস্টের জন্য CORS উন্মুক্ত রাখা
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class VideoRequest(BaseModel):
    url: str

class DownloadRequest(BaseModel):
    url: str
    formatId: str

@app.get("/")
def home():
    return {"status": "online", "message": "VideoDrop Backend Microservice is running!"}

@app.post("/analyze")
def analyze(req: VideoRequest):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=False)
            
            formats = []
            seen_heights = set()
            
            # ভিডিও কোয়ালিটি ফিল্টার (1080p, 720p, 480p, 360p)
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
                "downloadUrl": info.get('url') or req.url
            })

            # সময় ফরম্যাট করা (MM:SS)
            duration_sec = info.get('duration', 0)
            mins = int(duration_sec // 60)
            secs = int(duration_sec % 60)
            duration_str = f"{mins:02d}:{secs:02d}" if duration_sec else None

            return {
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
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/download")
def download(req: DownloadRequest):
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(req.url, download=False)
            
            # ইউজার যে কোয়ালিটি চেয়েছেন তার লিঙ্ক বের করা
            for f in info.get('formats', []):
                if req.formatId.replace('p', '') == str(f.get('height')) and f.get('url'):
                    return {
                        "downloadUrl": f.get('url'),
                        "filename": f"{info.get('title', 'video')}.mp4"
                    }
            return {
                "downloadUrl": info.get('url'),
                "filename": f"{info.get('title', 'video')}.mp4"
            }
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
