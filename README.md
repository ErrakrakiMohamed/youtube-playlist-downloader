# PlaylistGrabber 🚀

PlaylistGrabber is a modern, high-speed YouTube playlist downloader built with Flask and Python. It features a premium, responsive UI and uses a "Zero Disk Storage" approach—videos are streamed directly to your browser without taking up any space on the server.

## ✨ Features

- **Modern UI**: Dark-themed, glassmorphism design with smooth animations.
- **Playlist Scanning**: Quickly fetch metadata for entire playlists using `yt-dlp`.
- **Zero Storage**: Videos flow directly from YouTube CDN to the client via a streaming proxy.
- **Quality Options**: Choose from 1080p, 720p, 480p, and Audio-Only.
- **Batch Download**: One-click "Download All" for entire playlists.
- **Mobile Friendly**: Fully responsive design for all screen sizes.

## 🛠️ Technology Stack

- **Backend**: Python, Flask, `yt-dlp`
- **Frontend**: Modern HTML5, CSS3, JavaScript (Vanilla)
- **Deployment**: Render.com, Gunicorn

## 🚀 Running Locally

1.  Clone the repository:
    ```bash
    git clone https://github.com/YOUR_USERNAME/playlist-grabber.git
    cd playlist-grabber
    ```
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3.  Run the application:
    ```bash
    python app.py
    ```
4.  Open `http://localhost:5000` in your browser.

## 💰 Monetization

This app is pre-configured with ad slot placeholders. See [AD_SETUP_GUIDE.md](AD_SETUP_GUIDE.md) for instructions on how to set up Adsterra or other ad networks to monetize your site.

## 📜 Deployment

This project contains a `render.yaml` and `Procfile` for seamless deployment on [Render.com](https://render.com).

1.  Push code to GitHub.
2.  Create a "Web Service" on Render.
3.  Connect your repository and deploy!

---

*Disclaimer: This tool is for personal use only. Please respect YouTube's Terms of Service.*
