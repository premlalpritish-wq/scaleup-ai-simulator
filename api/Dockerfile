FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8080
WORKDIR /app
COPY project.godot ./project.godot
COPY api ./api
COPY composition/composition ./composition/composition
COPY composition/examples/ganjave_fed_batch.json ./composition/examples/ganjave_fed_batch.json
COPY composition/replay ./composition/replay
COPY Models/Ganjave ./Models/Ganjave
COPY Models/Morris ./Models/Morris
COPY Models/Zielinski ./Models/Zielinski
EXPOSE 8080
CMD ["python", "-m", "api.app"]
