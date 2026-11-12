FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FLOWCAPTURE_HOST=0.0.0.0 FLOWCAPTURE_DATA=/data PORT=8000
WORKDIR /app
COPY app.py ./
COPY static ./static
RUN useradd --create-home --uid 10001 flowcapture && mkdir /data && chown flowcapture:flowcapture /data
USER flowcapture
EXPOSE 8000
CMD ["python", "app.py"]
