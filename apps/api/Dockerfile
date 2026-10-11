FROM python:3.14-slim

RUN useradd --system --no-create-home api
WORKDIR /app
COPY micometeo_api ./micometeo_api
USER api
ENV MICOMETEO_API_HOST=0.0.0.0 MICOMETEO_API_PORT=8080
EXPOSE 8080
CMD ["python", "-m", "micometeo_api"]
