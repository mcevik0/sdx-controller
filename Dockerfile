FROM python:3.9-slim-bullseye

RUN apt-get update \
    && apt-get -y upgrade \
    && apt-get install -y --no-install-recommends gcc python3-dev git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /usr/src/app

WORKDIR /usr/src/app

WORKDIR /usr/src/app
COPY . /usr/src/app

RUN --mount=source=.git,target=.git,type=bind \
    pip install --no-cache-dir -e .

# RUN pip3 install --no-cache-dir .

EXPOSE 8080

ENTRYPOINT ["python3"]
CMD ["-m", "swagger_server"]
