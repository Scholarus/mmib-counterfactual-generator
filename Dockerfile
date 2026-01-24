# Use Python 3.9 slim image for smaller size
FROM python:3.9-slim

# 1. Install system dependencies including Xvfb for headless rendering
# We install these as root before switching users
RUN apt-get update && apt-get install -y \
    wget \
    xz-utils \
    xvfb \
    libx11-6 \
    libxxf86vm1 \
    libgl1 \
    libglu1-mesa \
    libxi6 \
    libxrender1 \
    libxfixes3 \
    libfontconfig1 \
    libxinerama1 \
    libxkbcommon0 \
    && rm -rf /var/lib/apt/lists/*

# 2. Set up a non-root user (Critical for Hugging Face Spaces)
# Spaces run as user ID 1000. If we don't do this, we get permission errors.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# Set working directory to the new user's home
WORKDIR $HOME/app

# 3. Install Blender (User-level install)
# Downloading to a folder the user owns
RUN wget -q https://download.blender.org/release/Blender3.6/blender-3.6.8-linux-x64.tar.xz -O /tmp/blender.tar.xz && \
    tar -xf /tmp/blender.tar.xz -C /tmp && \
    mkdir -p $HOME/blender && \
    mv /tmp/blender-3.6.8-linux-x64/* $HOME/blender/ && \
    rm -rf /tmp/blender.tar.xz /tmp/blender-3.6.8-linux-x64 && \
    # Add Blender to PATH so we can just type 'blender'
    echo 'export PATH="$HOME/blender:$PATH"' >> $HOME/.bashrc

# Update PATH for this session as well
ENV PATH="$HOME/blender:$PATH"

# Verify Blender installation
RUN blender --version

# 4. Install Python dependencies
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy application code with correct ownership
COPY --chown=user . .

# Create output directories that the user can write to
RUN mkdir -p $HOME/app/output $HOME/app/temp_output

# 6. Configuration for Hugging Face Spaces
# Spaces expect the app to listen on port 7860
ENV PORT=7860
EXPOSE 7860

# Healthcheck to ensure the container doesn't get killed
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:7860/_stcore/health || exit 1

# Set up Xvfb for headless rendering
ENV DISPLAY=:99

# 7. Run Streamlit on port 7860
CMD ["sh", "-c", "xvfb-run -a -s '-screen 0 1024x768x24' streamlit run app.py --server.port=7860 --server.address=0.0.0.0 --server.headless=true"]