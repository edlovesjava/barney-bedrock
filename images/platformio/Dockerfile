# barney + PlatformIO with espressif32 (ESP32, ESP32-S3) and native/Unity pre-installed.
# Build from the repo root:
#   docker build -f images/platformio/Dockerfile --build-arg BASE=barney -t barney-platformio .
ARG BASE=ghcr.io/edlovesjava/barney:latest
FROM ${BASE}

ENV PLATFORMIO_CORE_DIR=/opt/platformio
RUN pip install platformio

# Install platforms, toolchains, frameworks and Unity by building a seed project once.
COPY images/platformio/seed /tmp/seed
RUN cd /tmp/seed \
 && pio pkg install \
 && pio run -e esp32s3 -e esp32 \
 && pio test -e native --without-testing --without-uploading || true \
 && rm -rf /tmp/seed \
 && chmod -R a+rwX /opt/platformio

WORKDIR /work
