import os
import re
import time
import uuid
import yt_dlp
import requests as http_requests
from urllib.parse import urlparse, parse_qs
from flask import Flask, render_template, request, jsonify, Response

app = Flask(__name__)

# ── Temporary cache for extracted URLs (no files stored on disk) ──
url_cache = {}
CACHE_TTL = 300  # 5 minutes

# ── Quality format mapping (for yt-dlp fallback) ──
FORMAT_MAP = {
    'best':  'best[ext=mp4]/best',
    '1080p': 'best[height<=1080][ext=mp4]/best[height<=1080]',
    '720p':  'best[height<=720][ext=mp4]/best[height<=720]',
    '480p':  'best[height<=480][ext=mp4]/best[height<=480]',
    '360p':  'best[height<=360][ext=mp4]/best[height<=360]',
    'audio': 'bestaudio[ext=m4a]/bestaudio',
}

# ── Public Invidious instances (tried in order) ──
INVIDIOUS_INSTANCES = [
    'https://inv.nadeko.net',
    'https://invidious.nerdvpn.de',
    'https://invidious.projectsegfau.lt',
    'https://vid.puffyan.us',
    'https://invidious.lunar.icu',
    'https://iv.datura.network',
    'https://invidious.privacyredirect.com',
]

# ── Public Piped API instances (alternative to Invidious) ──
PIPED_INSTANCES = [
    'https://pipedapi.kavin.rocks',
    'https://pipedapi.adminforge.de',
    'https://pipedapi.in.projectsegfau.lt',
    'https://api.piped.yt',
    'https://pipedapi.r4fo.com',
]

# ── Quality height mapping ──
QUALITY_HEIGHT = {
    'best': 9999,
    '1080p': 1080,
    '720p': 720,
    '480p': 480,
    '360p': 360,
    'audio': 0,
}


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _cleanup_cache():
    now = time.time()
    expired = [k for k, v in url_cache.items() if v['expires'] < now]
    for k in expired:
        del url_cache[k]


def _sanitize_filename(name):
    return re.sub(r'[^\w\s\-\.\(\)\[\]]', '', name).strip() or 'video'


def _extract_youtube_ids(url):
    """Extract playlist_id and/or video_id from a YouTube URL."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    playlist_id = params.get('list', [None])[0]
    video_id = params.get('v', [None])[0]

    # Handle youtu.be short URLs
    host = parsed.hostname or ''
    if 'youtu.be' in host:
        video_id = parsed.path.strip('/')

    # Handle /playlist?list= URLs
    if not playlist_id and '/playlist' in parsed.path:
        playlist_id = params.get('list', [None])[0]

    return playlist_id, video_id


def _invidious_get(path, timeout=15):
    """Try getting data from multiple Invidious instances."""
    for instance in INVIDIOUS_INSTANCES:
        try:
            resp = http_requests.get(
                f'{instance}{path}',
                timeout=timeout,
                headers={'Accept': 'application/json'}
            )
            if resp.ok:
                return resp.json(), instance
        except Exception:
            continue
    return None, None


def _get_playlist_invidious(playlist_id):
    """Get playlist info from Invidious API."""
    data, _ = _invidious_get(f'/api/v1/playlists/{playlist_id}')
    if not data:
        return None

    videos = []
    for v in data.get('videos', []):
        vid = v.get('videoId', '')
        # Get the best available thumbnail
        thumbs = v.get('videoThumbnails', [])
        thumb_url = ''
        for t in thumbs:
            if t.get('quality') == 'medium':
                thumb_url = t.get('url', '')
                break
        if not thumb_url and thumbs:
            thumb_url = thumbs[0].get('url', '')
        # Fix relative thumbnail URLs
        if thumb_url and thumb_url.startswith('//'):
            thumb_url = 'https:' + thumb_url
        elif thumb_url and not thumb_url.startswith('http'):
            thumb_url = f'https://i.ytimg.com/vi/{vid}/mqdefault.jpg'

        videos.append({
            'id': vid,
            'title': v.get('title', 'Unknown'),
            'url': f'https://www.youtube.com/watch?v={vid}',
            'duration': v.get('lengthSeconds'),
            'thumbnail': thumb_url or f'https://i.ytimg.com/vi/{vid}/mqdefault.jpg',
        })

    return {
        'title': data.get('title', 'Playlist'),
        'video_count': len(videos),
        'videos': videos,
    }


def _get_video_stream_invidious(video_id, quality='best'):
    """Get video stream URL from Invidious API. Tries ALL instances."""
    target_height = QUALITY_HEIGHT.get(quality, 9999)
    is_audio = quality == 'audio'

    # Try every Invidious instance until one returns actual stream URLs
    for instance in INVIDIOUS_INSTANCES:
        try:
            resp = http_requests.get(
                f'{instance}/api/v1/videos/{video_id}',
                timeout=15,
                headers={'Accept': 'application/json'}
            )
            if not resp.ok:
                continue
            data = resp.json()
        except Exception:
            continue

        title = data.get('title', 'video')

        if is_audio:
            adaptive = data.get('adaptiveFormats', [])
            audio_streams = [f for f in adaptive if f.get('type', '').startswith('audio/') and f.get('url')]
            if audio_streams:
                audio_streams.sort(key=lambda x: x.get('bitrate', 0), reverse=True)
                stream = audio_streams[0]
                return {
                    'url': stream['url'],
                    'filename': f'{_sanitize_filename(title)}.m4a',
                    'filesize': stream.get('contentLength'),
                    'content_type': stream.get('type', 'audio/mp4').split(';')[0],
                }
        else:
            streams = data.get('formatStreams', [])
            streams = [s for s in streams if s.get('url')]  # Only streams with URLs
            if streams:
                streams.sort(key=lambda x: int(x.get('resolution', '0p').replace('p', '') or 0), reverse=True)
                best = streams[0]
                for s in streams:
                    h = int(s.get('resolution', '0p').replace('p', '') or 0)
                    if h <= target_height:
                        best = s
                        break
                return {
                    'url': best['url'],
                    'filename': f'{_sanitize_filename(title)}.{best.get("container", "mp4")}',
                    'filesize': best.get('contentLength'),
                    'content_type': best.get('type', 'video/mp4').split(';')[0],
                }
    return None


def _get_video_stream_piped(video_id, quality='best'):
    """Get video stream URL from Piped API. Tries ALL instances."""
    target_height = QUALITY_HEIGHT.get(quality, 9999)
    is_audio = quality == 'audio'

    for instance in PIPED_INSTANCES:
        try:
            resp = http_requests.get(
                f'{instance}/streams/{video_id}',
                timeout=15,
                headers={'Accept': 'application/json'}
            )
            if not resp.ok:
                continue
            data = resp.json()
        except Exception:
            continue

        title = data.get('title', 'video')

        if is_audio:
            audio_streams = data.get('audioStreams', [])
            audio_streams = [s for s in audio_streams if s.get('url')]
            if audio_streams:
                audio_streams.sort(key=lambda x: x.get('bitrate', 0), reverse=True)
                stream = audio_streams[0]
                ext = 'mp3' if 'mpeg' in stream.get('mimeType', '') else 'm4a'
                return {
                    'url': stream['url'],
                    'filename': f'{_sanitize_filename(title)}.{ext}',
                    'filesize': stream.get('contentLength'),
                    'content_type': stream.get('mimeType', 'audio/mp4').split(';')[0],
                }
        else:
            video_streams = data.get('videoStreams', [])
            # Filter: only streams with both video and audio (not video-only)
            combined = [s for s in video_streams if s.get('url') and s.get('videoOnly') is False]
            if not combined:
                # Fallback: use any video stream with a URL
                combined = [s for s in video_streams if s.get('url')]
            if combined:
                combined.sort(key=lambda x: x.get('height', 0) or 0, reverse=True)
                best = combined[0]
                for s in combined:
                    if (s.get('height', 0) or 0) <= target_height:
                        best = s
                        break
                ext = 'mp4' if 'mp4' in best.get('mimeType', '') else 'webm'
                return {
                    'url': best['url'],
                    'filename': f'{_sanitize_filename(title)}.{ext}',
                    'filesize': best.get('contentLength'),
                    'content_type': best.get('mimeType', 'video/mp4').split(';')[0],
                }
    return None


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/playlist-info', methods=['POST'])
def playlist_info():
    """Fetch playlist metadata using Invidious API (with yt-dlp fallback)."""
    data = request.get_json()
    url = data.get('url', '').strip()

    if not url:
        return jsonify({'error': 'Please provide a playlist URL.'}), 400

    playlist_id, video_id = _extract_youtube_ids(url)

    # ── If it's a single video URL (no playlist), wrap it as a 1-video list ──
    if not playlist_id and video_id:
        vid_data, _ = _invidious_get(f'/api/v1/videos/{video_id}')
        if vid_data:
            thumbs = vid_data.get('videoThumbnails', [])
            thumb = ''
            for t in thumbs:
                if t.get('quality') == 'medium':
                    thumb = t.get('url', '')
                    break
            if thumb and thumb.startswith('//'):
                thumb = 'https:' + thumb

            return jsonify({
                'title': vid_data.get('title', 'Single Video'),
                'video_count': 1,
                'videos': [{
                    'id': video_id,
                    'title': vid_data.get('title', 'Video'),
                    'url': f'https://www.youtube.com/watch?v={video_id}',
                    'duration': vid_data.get('lengthSeconds'),
                    'thumbnail': thumb or f'https://i.ytimg.com/vi/{video_id}/mqdefault.jpg',
                }]
            })
        return jsonify({'error': 'Could not fetch video info. The video may be unavailable.'}), 400

    if not playlist_id:
        return jsonify({'error': 'Could not find a playlist ID in the URL. Please paste a valid YouTube playlist URL.'}), 400

    # ── Try Invidious first ──
    result = _get_playlist_invidious(playlist_id)
    if result and result['videos']:
        return jsonify(result)

    # ── Fallback: try yt-dlp ──
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'skip_download': True,
            'ignoreerrors': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if info:
            entries = info.get('entries', [])
            videos = []
            for i, entry in enumerate(entries):
                if entry:
                    vid = entry.get('id', '')
                    videos.append({
                        'id': vid,
                        'title': entry.get('title', f'Video {i + 1}'),
                        'url': f'https://www.youtube.com/watch?v={vid}',
                        'duration': entry.get('duration'),
                        'thumbnail': f'https://i.ytimg.com/vi/{vid}/mqdefault.jpg',
                    })
            if videos:
                return jsonify({
                    'title': info.get('title', 'Playlist'),
                    'video_count': len(videos),
                    'videos': videos,
                })
    except Exception:
        pass

    return jsonify({'error': 'Could not extract playlist info. All extraction methods failed. Please check the URL.'}), 400


@app.route('/api/extract-url', methods=['POST'])
def extract_url():
    """Extract direct download URL using Invidious (with yt-dlp fallback)."""
    _cleanup_cache()

    data = request.get_json()
    video_url = data.get('url', '').strip()
    quality = data.get('quality', 'best')

    if not video_url:
        return jsonify({'error': 'No video URL provided.'}), 400

    _, video_id = _extract_youtube_ids(video_url)
    if not video_id:
        return jsonify({'error': 'Could not extract video ID from URL.'}), 400

    # ── Try Invidious first ──
    stream_info = _get_video_stream_invidious(video_id, quality)
    if stream_info and stream_info.get('url'):
        token = str(uuid.uuid4())
        url_cache[token] = {
            'direct_url': stream_info['url'],
            'headers': {},
            'filename': stream_info['filename'],
            'filesize': stream_info.get('filesize'),
            'content_type': stream_info.get('content_type', 'video/mp4'),
            'expires': time.time() + CACHE_TTL,
        }
        return jsonify({
            'token': token,
            'filename': stream_info['filename'],
            'filesize': stream_info.get('filesize'),
        })

    # ── Try Piped API ──
    stream_info = _get_video_stream_piped(video_id, quality)
    if stream_info and stream_info.get('url'):
        token = str(uuid.uuid4())
        url_cache[token] = {
            'direct_url': stream_info['url'],
            'headers': {},
            'filename': stream_info['filename'],
            'filesize': stream_info.get('filesize'),
            'content_type': stream_info.get('content_type', 'video/mp4'),
            'expires': time.time() + CACHE_TTL,
        }
        return jsonify({
            'token': token,
            'filename': stream_info['filename'],
            'filesize': stream_info.get('filesize'),
        })

    # ── Fallback: try yt-dlp with multiple strategies ──
    chosen_format = FORMAT_MAP.get(quality, FORMAT_MAP['best'])
    strategies = [
        {'extractor_args': {'youtube': {'player_client': ['ios', 'android']}},
         'http_headers': {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15'}},
        {'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
         'http_headers': {'User-Agent': 'Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36'}},
        {'extractor_args': {'youtube': {'player_client': ['web']}},
         'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}},
    ]

    for strategy in strategies:
        try:
            ydl_opts = {
                'format': chosen_format, 'quiet': True, 'no_warnings': True,
                'noplaylist': True, 'socket_timeout': 30, 'retries': 2,
                **strategy,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
            if info:
                direct_url = info.get('url')
                if not direct_url:
                    fmts = info.get('requested_formats', [])
                    if fmts:
                        direct_url = fmts[0].get('url')
                if direct_url:
                    token = str(uuid.uuid4())
                    url_cache[token] = {
                        'direct_url': direct_url,
                        'headers': info.get('http_headers', {}),
                        'filename': f"{_sanitize_filename(info.get('title', 'video'))}.{info.get('ext', 'mp4')}",
                        'filesize': info.get('filesize') or info.get('filesize_approx'),
                        'expires': time.time() + CACHE_TTL,
                    }
                    return jsonify({
                        'token': token,
                        'filename': url_cache[token]['filename'],
                        'filesize': url_cache[token]['filesize'],
                    })
        except Exception:
            continue

    return jsonify({'error': 'Could not extract download URL. All methods failed for this video.'}), 400


@app.route('/api/download/<token>')
def proxy_download(token):
    """Stream the video from CDN through the server (zero disk storage)."""
    cached = url_cache.pop(token, None)

    if not cached or cached['expires'] < time.time():
        return jsonify({'error': 'Download link expired. Please try again.'}), 410

    try:
        cdn_resp = http_requests.get(
            cached['direct_url'],
            headers=cached.get('headers', {}),
            stream=True,
            timeout=30,
        )
        cdn_resp.raise_for_status()

        content_length = cdn_resp.headers.get('Content-Length', '')
        content_type = cached.get('content_type') or cdn_resp.headers.get('Content-Type', 'application/octet-stream')

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
