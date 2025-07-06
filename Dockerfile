# Use a minimal, actively-maintained image to reduce the attack surface.
FROM python:3.11-slim-bullseye

# Prevent Python from writing .pyc files and buffering stdout/err.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create a non-root user to run the application more safely.
RUN addgroup --system app && adduser --system --ingroup app app

# Install build dependencies only if they are really needed and
# remove cached package lists to keep the final image small.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set work directory.
WORKDIR /app

# Install Python dependencies first to leverage Docker layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application source.
COPY . .

# Ensure the non-root user owns the code.
RUN chown -R app:app /app

USER app

# Expose the TCP port used by socket-server.py
EXPOSE 65432

# Default command.
CMD ["python", "socket-server.py"]
ENTRYPOINT ["python", "socket-server.py"]