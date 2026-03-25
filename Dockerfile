FROM astral/uv:python3.12-bookworm-slim

WORKDIR /app

RUN --mount=target=/var/lib/apt/lists,type=cache,sharing=locked \
    --mount=target=/var/cache/apt,type=cache,sharing=locked \
    apt update -y && \
    apt install -y ffmpeg

COPY __main__.py pyproject.toml uv.lock /app/

RUN uv sync

ENTRYPOINT ["uv", "run", "python", "__main__.py"]