FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

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

RUN python3 -m venv --system-site-packages /workspace/.venv \
  && . /workspace/.venv/bin/activate \
  && python -m pip install --upgrade pip setuptools wheel \
  && python -m pip install -r requirements-dev.txt

ENV VIRTUAL_ENV=/workspace/.venv \
    PATH="/workspace/.venv/bin:${PATH}"

CMD ["/bin/bash"]
