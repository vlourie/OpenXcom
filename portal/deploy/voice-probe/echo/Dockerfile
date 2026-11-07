# Echo bot of the voice probe: the official LiveKit Python SDK (livekit = realtime, livekit-api = tokens)
FROM python:3.12-slim
RUN pip install --no-cache-dir livekit==1.1.20 livekit-api==1.2.1
WORKDIR /app
COPY echo.py .
ENV PYTHONUNBUFFERED=1
CMD ["python", "echo.py"]
