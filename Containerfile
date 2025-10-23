# ============================================
# Builder Stage: Compile dependencies
# ============================================
FROM registry.access.redhat.com/ubi9-minimal AS builder

# Install build dependencies and Python
RUN microdnf install -y --setopt=install_weak_deps=0 \
    python3.12-devel \
    postgresql-devel \
    gcc \
    tar \
    gzip \
    findutils && \
    python3.12 -m ensurepip --upgrade && \
    pip3 install --no-cache-dir uv && \
    microdnf clean all -y && \
    rm -rf /var/cache/dnf/* /var/cache/yum/* /tmp/* /var/tmp/*

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install Python dependencies
# Introduce INSTALL_ML to control the installation of local-ml dependencies
# if INSTALL_ML is true, install local-ml dependencies
# if INSTALL_ML is false, install dependencies without local-ml (Default. Not necessary if not using local embeddings models)

ARG INSTALL_ML=false
RUN if [ "$INSTALL_ML" = "true" ]; then \
        uv sync --no-dev --group local-ml --no-cache; \
    else \
        uv sync --no-dev --no-group local-ml --no-cache; \
    fi && \
    find /app/.venv -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true && \
    find /app/.venv -type f -name '*.pyc' -delete && \
    find /app/.venv -type f -name '*.pyo' -delete && \
    rm -rf /root/.cache /tmp/*

# ============================================
# Runtime Stage: Minimal production image
# ============================================
FROM registry.access.redhat.com/ubi9-minimal

# Install only runtime dependencies (no build tools)
RUN microdnf install -y --setopt=install_weak_deps=0 \
    python3.12 \
    postgresql && \
    microdnf clean all -y && \
    rm -rf /var/cache/dnf/* /var/cache/yum/* /var/log/dnf* /var/log/yum*

# Create a non-root user for security
RUN groupadd -r boann && useradd -u 1000 -r -g boann -m -d /app boann && \
    chown -R 1000 /app && \
    # OpenShift runs containers with arbitrary user ids, belonging to root group
    chgrp -R 0 /app && \
    chmod -R g=u /app

WORKDIR /app

# Copy compiled dependencies from builder
COPY --from=builder --chown=1000:0 /app/.venv /app/.venv
COPY --from=builder --chown=1000:0 /app/pyproject.toml /app/uv.lock ./

# Copy application source code
COPY --chown=1000:0 src/ ./src/
COPY --chown=1000:0 scripts/start_boann.py ./scripts/
COPY --chown=1000:0 scripts/ingest_documents.py ./scripts/
COPY --chown=1000:0 scripts/shutdown_boann.py ./scripts/
COPY --chown=1000:0 examples/config/ ./examples/config/

USER boann

# Expose the API port
EXPOSE 8000

# Default environment variables (can be overridden at runtime)
ENV LLAMA_STACK_HOST=localhost \
    LLAMA_STACK_PORT=8321 \
    BOANN_HOST=0.0.0.0 \
    BOANN_PORT=8000 \
    LLAMA_STACK_CONFIG_PATH=examples/config/run-starter-remote-minimal.yaml \
    LLAMASTACK_STARTUP_TIMEOUT=60 \
    HEALTH_CHECK_TIMEOUT=10 \
    HEALTH_CHECK_INTERVAL=2 \
    PATH="/app/.venv/bin:$PATH"

# Start the Boann system using the startup script
CMD ["python3", "scripts/start_boann.py"]
