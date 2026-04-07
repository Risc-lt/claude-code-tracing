FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY visualizer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy visualizer source code
COPY visualizer/ .

RUN chmod +x /app/visualizer/visualize.sh

# Trace files are mounted at /app/logs via docker-compose
RUN mkdir -p /app/logs

EXPOSE 8080

# Serve the web visualizer; run analysis via `docker exec`
CMD ["python3", "-m", "http.server", "8080", "--bind", "0.0.0.0"]
