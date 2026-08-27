# Opening Lead Simulator — API image.
FROM python:3.12-slim

# endplay's bundled double-dummy solver (a compiled .so) links against the
# OpenMP runtime; libgomp1 is the one non-obvious dependency on slim images.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY engine ./engine
COPY app ./app

# DDS thread cap (see engine/dds_runtime.py). Overridden by compose; 0 = all cores.
ENV BRIDGE_DDS_THREADS=4

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
