# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Install system dependencies needed for Pygame (SDL libraries) and X11 GUI rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsdl2-2.0-0 \
    libsdl2-image-2.0-0 \
    libsdl2-mixer-2.0-0 \
    libsdl2-ttf-2.0-0 \
    libx11-6 \
    x11-apps \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the dependency specs first (optimization for build caching)
COPY requirements.txt .

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source code
COPY . .

# Set working directory to the game folder containing tetris.py
WORKDIR /app/tetris

# Instructions on running the GUI container:
#
# A. For Linux or WSL2 (WSLg active):
#    1. Build the image:
#       docker build -t tetris-duo .
#    2. Run with display socket sharing:
#       docker run --rm -it -e DISPLAY=$DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix tetris-duo
#
# B. For Windows (with VcXsrv / Xming / X-Server running):
#    1. Build the image:
#       docker build -t tetris-duo .
#    2. Run with Host IP loopback forwarding (ensure X-server allows public access / no access control):
#       docker run --rm -it -e DISPLAY=host.docker.internal:0.0 tetris-duo

CMD ["python", "tetris.py"]
