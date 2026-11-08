FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8080
WORKDIR /app
COPY api/__init__.py ./api/__init__.py
COPY api/app.py ./api/app.py
COPY api/research.py ./api/research.py
COPY composition/composition ./composition/composition
COPY composition/workflow ./composition/workflow
COPY composition/examples/ganjave_fed_batch.json ./composition/examples/ganjave_fed_batch.json
COPY composition/replay ./composition/replay
COPY composition/workflow_runs ./composition/workflow_runs
COPY Models/Ganjave ./Models/Ganjave
COPY Models/Morris ./Models/Morris
COPY Models/Zielinski ./Models/Zielinski
COPY web/research ./web/research
EXPOSE 8080
CMD ["python", "-m", "api.app"]
