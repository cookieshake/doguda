FROM ghcr.io/astral-sh/uv:python3.13-trixie

WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy project definition
COPY pyproject.toml uv.lock /app/

# Install dependencies (frozen in uv.lock) without installing the project itself
RUN uv sync --frozen --no-install-project --no-dev

# Copy the rest of the source code
COPY . /app

# Install the project
RUN uv sync --frozen --no-dev

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"
# Ensure src modules are importable
ENV PYTHONPATH="/app/src:$PYTHONPATH"

# Default environment variable
ENV DOGUDA_MODULE=doguda_app

# Expose port
EXPOSE 8000

# Run command
CMD ["doguda", "serve"]
