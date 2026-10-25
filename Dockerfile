# The 420 API — free read-only API for The Official 420 World Clock (api.420.menow.us). Base pinned by digest (Python 3.14.8).
FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170
# PYTHONTZPATH empty: use the pinned tzdata package, never the image's older system zoneinfo.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONTZPATH=
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ /app/
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD ["python","-c","import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4)"]
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8000","--proxy-headers","--forwarded-allow-ips","*","--no-server-header"]
