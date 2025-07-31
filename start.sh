#!/bin/bash

# Download static FFmpeg if not already present
if [ ! -f "./ffmpeg" ]; then
  echo "Downloading FFmpeg..."
  curl -L https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz -o ffmpeg.tar.xz
  tar -xf ffmpeg.tar.xz
  mv ffmpeg-*-amd64-static/ffmpeg .
  chmod +x ffmpeg
fi

# Start the Flask app using gunicorn
echo "Starting Flask app..."
exec gunicorn app:app --bind 0.0.0.0:$PORT
