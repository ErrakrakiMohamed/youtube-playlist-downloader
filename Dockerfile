# Use Python 3.11 Slim
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PORT=7860

# Install system dependencies (ffmpeg is required for yt-dlp)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create a local storage folder (though it will be temporary)
RUN mkdir -p /app/downloads && chmod 777 /app/downloads

# Expose the correct port for Hugging Face
EXPOSE 7860

# Run the application
CMD ["python", "app.py"]
