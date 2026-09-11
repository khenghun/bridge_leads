# Bridge backend image — carries both app packages plus the shared engine.
# Two targets:
#   backend  (default for the API containers) — the lead container runs the
#            CMD below; the play container overrides `command:` in its compose
#            file (uvicorn app_play.main:app).
#   worker   — the same image plus the AWS Lambda runtime client and the play
#            solver's worker handler (docs/play/v1.5-lambda-strict-plan.md).
#            Built and pushed to ECR by CI with the same tags as the API image,
#            so the pair can be deployed together.
# Build the API with `--target backend` (compose files and CI do) — a plain
# `docker build` of a multi-stage file produces the LAST stage, the worker.
FROM python:3.12-slim AS backend

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
COPY app_play ./app_play

# DDS thread cap (see engine/dds_runtime.py). Overridden by compose; 0 = all cores.
ENV BRIDGE_DDS_THREADS=4

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


# ---------------------------------------------------------------------------
# Play worker (AWS Lambda, container image). awslambdaric is the runtime
# interface client that talks to the Lambda service; the handler is
# worker/handler.py. The thread cap stays 4 for schedule parity with prod
# (the inner judgement's first batch is max(5, threads) — see the plan).
FROM backend AS worker

RUN pip install --no-cache-dir awslambdaric

COPY worker ./worker

# endplay imports matplotlib on package import; on Lambda the home directory
# is read-only, so without this matplotlib warns and rebuilds its font cache
# in a fresh temp dir on every cold start.
ENV MPLCONFIGDIR=/tmp/matplotlib

ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["worker.handler.handler"]
