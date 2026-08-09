FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --create-home --uid 10002 db-viewer
COPY --chown=db-viewer:db-viewer app.py reset_actions.py ./
COPY --chown=db-viewer:db-viewer .streamlit ./.streamlit

EXPOSE 8501
USER db-viewer
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
