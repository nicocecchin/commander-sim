# Self-contained image: Java 21, this package and the pinned Forge release.
# Build:  docker build -t commander-sim .
# Run:    docker run --rm -v "$PWD/work:/work" commander-sim run /work/bundle/job.yaml --runs-dir /work/runs
FROM eclipse-temurin:21-jre-noble

COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /usr/local/bin/uv

# Python and the virtualenv live outside /root so the container can run as any user.
ENV UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH=/app/.venv/bin:$PATH

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev && chmod -R a+rX /opt/python /app
RUN commander-sim forge setup && chmod -R a+rX /app/vendor

ENTRYPOINT ["commander-sim"]
