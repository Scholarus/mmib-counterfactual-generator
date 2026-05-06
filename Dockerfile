FROM python:3.9-slim

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

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

RUN wget -q https://download.blender.org/release/Blender3.6/blender-3.6.8-linux-x64.tar.xz -O /tmp/blender.tar.xz && \
    tar -xf /tmp/blender.tar.xz -C /tmp && \
    mkdir -p $HOME/blender && \
    mv /tmp/blender-3.6.8-linux-x64/* $HOME/blender/ && \
    rm -rf /tmp/blender.tar.xz /tmp/blender-3.6.8-linux-x64 && \
    echo 'export PATH="$HOME/blender:$PATH"' >> $HOME/.bashrc

ENV PATH="$HOME/blender:$PATH"

RUN blender --version

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .

RUN mkdir -p $HOME/app/output $HOME/app/temp_output

ENV PORT=7860
EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:7860/_stcore/health || exit 1

ENV DISPLAY=:99

CMD ["sh", "-c", "xvfb-run -a -s '-screen 0 1024x768x24' streamlit run app.py --server.port=7860 --server.address=0.0.0.0 --server.headless=true"]