#!/bin/bash

# Install FFmpeg
apt-get update
apt-get install -y ffmpeg

# Now run the app (you can replace this line with your own start command)
python3 app.py
