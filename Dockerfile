FROM python:3.13-slim

WORKDIR /queimadas

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn

COPY . .

EXPOSE 5000

CMD ["gunicorn", "--chdir", "src", "--preload", "--bind", "0.0.0.0:5000", "src.api:api"]
