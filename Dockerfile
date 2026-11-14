FROM rust:1.92-bookworm AS rust-build
WORKDIR /build
COPY Cargo.toml Cargo.lock ./
COPY src ./src
COPY config ./config
RUN cargo build --locked --release

FROM debian:bookworm-slim AS whisper-build
ARG WHISPER_VERSION=v1.9.5
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git cmake g++ make && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch "$WHISPER_VERSION" https://github.com/ggml-org/whisper.cpp.git /whisper
RUN cmake -S /whisper -B /whisper/build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DGGML_NATIVE=OFF -DGGML_OPENMP=OFF -DWHISPER_BUILD_TESTS=OFF && cmake --build /whisper/build --target whisper-cli -j 2

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates chromium chromium-sandbox ffmpeg xvfb x11vnc fonts-noto-cjk curl && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /usr/share/novnc && curl -fsSL https://github.com/novnc/noVNC/archive/refs/tags/v1.6.0.tar.gz | tar -xz -C /usr/share/novnc --strip-components=1 && rm -rf /usr/share/novnc/utils /usr/share/novnc/tests /usr/share/novnc/.github

COPY --from=rust-build /build/target/release/shared-video-transcriber /usr/local/bin/shared-video-transcriber
COPY --from=whisper-build /whisper/build/bin/whisper-cli /usr/local/bin/whisper-cli
RUN useradd -m -u 1000 transcriber && mkdir -p /data /models && chown transcriber:transcriber /data /models
USER transcriber
WORKDIR /home/transcriber
ENV VIDEO_DATA_DIR=/data WHISPER_MODEL=/models/ggml-small.bin
EXPOSE 6080
ENTRYPOINT ["shared-video-transcriber"]
CMD ["--help"]
