# Custom run image for Google Cloud Buildpacks with OpenGL support
# This image includes system libraries required by skia-python for rendering

FROM gcr.io/buildpacks/gcp/run

# Switch to root to install packages
USER root

# Install OpenGL/EGL libraries required by skia-python
RUN apt-get update && apt-get install -y --no-install-recommends \
    libegl1 \
    libgl1 \
    libgles2 \
    libgomp1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Switch back to the non-root user (required by buildpacks)
USER 33:33
