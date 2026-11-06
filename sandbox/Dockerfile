FROM python:3.12-slim
RUN pip install --no-cache-dir pandas==2.2.* matplotlib==3.9.*
WORKDIR /work
COPY worker.py /work/worker.py
# Run as nobody, never root
USER 65534:65534
CMD ["python", "/work/worker.py"]
