FROM python:3.12-slim-bookworm

# Prevent python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PORT=8080

# Install system dependencies and Node.js 20
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    libsndfile1 \
    procps \
    git \
    ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1. Install Python dependencies
COPY the_folder_for_product/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# 2. Build React Frontend
COPY the_folder_for_product/frontend/package*.json /app/frontend/
RUN cd /app/frontend && npm install
COPY the_folder_for_product/frontend /app/frontend
RUN cd /app/frontend && npm run build

# 3. Install Node dependencies for server.js
COPY the_folder_for_product/package*.json /app/
RUN npm install --omit=dev

# 4. Copy application product files
COPY the_folder_for_product/ /app/

# Ensure compiled frontend assets are in place
COPY the_folder_for_product/frontend/dist /app/frontend/dist

# 5. Production launcher
COPY start_railway.sh /app/start_railway.sh
RUN chmod +x /app/start_railway.sh

EXPOSE 8080

CMD ["/app/start_railway.sh"]
