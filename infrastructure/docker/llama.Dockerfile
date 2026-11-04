# llama.cpp's server, built from the release the benchmarks used. MIT licence.
FROM debian:bookworm-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake git ca-certificates
RUN git clone --depth 1 --branch b12098 https://github.com/ggml-org/llama.cpp /src
RUN cmake -S /src -B /build -DCMAKE_BUILD_TYPE=Release -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=ON \
 && cmake --build /build --target llama-server -j

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl && rm -rf /var/lib/apt/lists/*
COPY --from=build /build/bin/ /usr/local/bin/
USER 10001
ENTRYPOINT ["llama-server"]
