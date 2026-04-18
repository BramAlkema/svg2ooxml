FROM python:3.14-slim

ARG FONTFORGE_REF=a01d2ebf2013b8de6c7972cab1f962400bd93171

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/svg2ooxml-venv \
    XDG_CACHE_HOME=/var/cache \
    SVG2OOXML_FONT_CACHE_DIR=/var/cache/svg2ooxml/fonts \
    SVG2OOXML_TEMP_DIR=/var/tmp/svg2ooxml \
    SVG2OOXML_REPORTS_DIR=/workspace/reports \
    SVG2OOXML_W3C_OUTPUT=/workspace/tests/corpus/w3c/output

# We want Python 3.14 parity between the local .venv and the reproducible Linux
# render lane. FontForge's official Python packaging exists upstream but is not
# yet a public PyPI release we can consume directly here, so we build it from a
# pinned upstream commit.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    ninja-build \
    pkg-config \
    gettext \
    git \
    libxml2-dev \
    zlib1g-dev \
    libfreetype6-dev \
    libpng-dev \
    libjpeg62-turbo-dev \
    libtiff-dev \
    libbrotli-dev \
    libspiro-dev \
    libwoff-dev \
    libharfbuzz-dev \
    libpango1.0-dev \
    libcairo2-dev \
    libglib2.0-dev \
    libfontconfig1-dev \
    libegl1 \
    libgl1 \
    libgles2 \
    fonts-dejavu-core \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY . /workspace

RUN mkdir -p /var/cache/svg2ooxml/fonts \
  /var/tmp/svg2ooxml \
  /workspace/reports \
  /workspace/tests/corpus/w3c/output \
  && python -m venv "$VIRTUAL_ENV" \
  && . "$VIRTUAL_ENV/bin/activate" \
  && python -m pip install --upgrade pip setuptools wheel \
  && git clone https://github.com/fontforge/fontforge.git /tmp/fontforge-src \
  && cd /tmp/fontforge-src \
  && git checkout -q "$FONTFORGE_REF" \
  && sed -i 's/COMPONENTS Development.Module Interpreter/COMPONENTS Development Development.Module Interpreter/' CMakeLists.txt \
  && python -m pip install . \
  && rm -rf /tmp/fontforge-src \
  && cd /workspace \
  && python -m pip install -e .[dev,api,cloud,render,color,slides,payments,visual-testing]

ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

CMD ["/bin/bash"]
