import os
import re
import time
import uuid
import yt_dlp
import requests as http_requests
from flask import Flask, render_template, request, jsonify, Response

app = Flask(__name__)

# ── Temporary cache for extracted URLs (no files stored on disk) ──
url_cache = {}
CACHE_TTL = 300  # 5 minutes

# ── Quality format mapping (pre-merged formats preferred) ──
FORMAT_MAP = {
    'best':  'best[ext=mp4]/best',
    '1080p': 'best[height<=1080][ext=mp4]/best[height<=1080]',
    '720p':  'best[height<=720][ext=mp4]/best[height<=720]',
    '480p':  'best[height<=480][ext=mp4]/best[height<=480]',
    '360p':  'best[height<=360][ext=mp4]/best[height<=360]',
    'audio': 'bestaudio[ext=m4a]/bestaudio',
}


def _cleanup_cache():
    """Remove expired cache entries."""
    now = time.time()
    expired = [k for k, v in url_cache.items() if v['expires'] < now]
    for k in expired:
        del url_cache[k]


def _sanitize_filename(name):
    """Remove characters that are unsafe for filenames."""
    return re.sub(r'[^\w\s\-\.\(\)\[\]]', '', name).strip() or 'video'


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/playlist-info', methods=['POST'])
def playlist_info():
    """Fetch playlist metadata without downloading anything."""
    data = request.get_json()
    url = data.get('url', '').strip()

    if not url:
        return jsonify({'error': 'Please provide a playlist URL.'}), 400

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'skip_download': True,
        'ignoreerrors': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'web'],
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1',
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if info is None:
            return jsonify({'error': 'Could not extract playlist info. Check the URL.'}), 400

        entries = info.get('entries', [])
        videos = []
        for i, entry in enumerate(entries):
            if entry:
                vid = entry.get('id', '')
                videos.append({
                    'id': vid,
                    'title': entry.get('title', f'Video {i + 1}'),
                    'url': f'https://www.youtube.com/watch?v={vid}' if vid else '',
                    'duration': entry.get('duration'),
                    'thumbnail': f'https://i.ytimg.com/vi/{vid}/mqdefault.jpg' if vid else '',
                })

        return jsonify({
            'title': info.get('title', 'Unknown Playlist'),
            'video_count': len(videos),
            'videos': videos,
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/extract-url', methods=['POST'])
def extract_url():
    """Extract direct download URL, cache it, and return a one-time token."""
    _cleanup_cache()

    data = request.get_json()
    video_url = data.get('url', '').strip()
    quality = data.get('quality', 'best')

    if not video_url:
        return jsonify({'error': 'No video URL provided.'}), 400

    chosen_format = FORMAT_MAP.get(quality, FORMAT_MAP['best'])

    ydl_opts = {
        'format': chosen_format,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'web'],
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1',
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)

        if info is None:
            return jsonify({'error': 'Could not extract video info.'}), 400

        # Get the direct stream URL
        direct_url = info.get('url')
        if not direct_url:
            formats = info.get('requested_formats', [])
            if formats:
                direct_url = formats[0].get('url')

        if not direct_url:
            return jsonify({'error': 'Could not extract a download URL for this video.'}), 400

        title = info.get('title', 'video')
        ext = info.get('ext', 'mp4')
        filename = f"{_sanitize_filename(title)}.{ext}"
        http_headers = info.get('http_headers', {})
        filesize = info.get('filesize') or info.get('filesize_approx')

        # Store in short-lived cache
        token = str(uuid.uuid4())
        url_cache[token] = {
            'direct_url': direct_url,
            'headers': http_headers,
            'filename': filename,
            'filesize': filesize,
            'expires': time.time() + CACHE_TTL,
        }

        return jsonify({
            'token': token,
            'filename': filename,
            'filesize': filesize,
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/download/<token>')
def proxy_download(token):
    """Stream the video from YouTube CDN through the server (zero disk storage).
    The response has Content-Disposition: attachment so the browser downloads it."""
    cached = url_cache.pop(token, None)

    if not cached or cached['expires'] < time.time():
        return jsonify({'error': 'Download link expired. Please try again.'}), 410

    try:
        cdn_resp = http_requests.get(
            cached['direct_url'],
            headers=cached['headers'],
            stream=True,
            timeout=30,
        )
        cdn_resp.raise_for_status()

        content_length = cdn_resp.headers.get('Content-Length', '')
        content_type = cdn_resp.headers.get('Content-Type', 'application/octet-stream')

        def generate():
            try:
                for chunk in cdn_resp.iter_content(chunk_size=65536):
                    if chunk:
                        yield chunk
            finally:
                cdn_resp.close()

        resp_headers = {
            'Content-Disposition': f'attachment; filename="{cached["filename"]}"',
            'Content-Type': content_type,
            'Cache-Control': 'no-cache',
        }
        if content_length:
            resp_headers['Content-Length'] = content_length

        return Response(generate(), headers=resp_headers)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 7860))
    print(f"\n>>> PlaylistGrabber — YouTube Playlist Downloader (Port: {port})")
    print(f"    Open http://localhost:{port} in your browser\n")
    app.run(debug=True, host='0.0.0.0', port=port, threaded=True)
