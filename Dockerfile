FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    XDG_CACHE_HOME=/var/cache \
    SVG2OOXML_FONT_CACHE_DIR=/var/cache/svg2ooxml/fonts \
    SVG2OOXML_TEMP_DIR=/var/tmp/svg2ooxml \
    SVG2OOXML_REPORTS_DIR=/workspace/reports \
    SVG2OOXML_W3C_OUTPUT=/workspace/tests/corpus/w3c/output

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-venv \
    python3-pip \
    python3-fontforge \
    fontforge \
    libegl1 \
    libgl1 \
    libgles2 \
    git \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY . /workspace

RUN mkdir -p /var/cache/svg2ooxml/fonts \
  /var/tmp/svg2ooxml \
  /workspace/reports \
  /workspace/tests/corpus/w3c/output \
  && python3 -m venv --system-site-packages /workspace/.venv \
  && . /workspace/.venv/bin/activate \
  && python -m pip install --upgrade pip setuptools wheel \
  && python -m pip install -r requirements-dev.txt

ENV VIRTUAL_ENV=/workspace/.venv \
    PATH="/workspace/.venv/bin:${PATH}"

CMD ["/bin/bash"]
