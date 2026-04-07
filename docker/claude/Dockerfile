FROM node:22-bookworm

# Install system deps Claude Code may need
RUN apt-get update && apt-get install -y \
    git \
    curl \
    ripgrep \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Point Claude Code at the LiteLLM proxy (resolved via docker-compose service name)
ENV ANTHROPIC_BASE_URL=http://litellm-proxy:4000
ENV ANTHROPIC_AUTH_TOKEN=sk-my-litellm-key

WORKDIR /workspace

# Keep the container running so you can exec into it
CMD ["sleep", "infinity"]
