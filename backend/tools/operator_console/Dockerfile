FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --create-home --uid 10001 operator-console
COPY --chown=operator-console:operator-console app.py api_client.py ./
COPY --chown=operator-console:operator-console .streamlit ./.streamlit

EXPOSE 8501
USER operator-console
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
