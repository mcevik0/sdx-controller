# SDX Controller service

## Overview
This SDX Controller server was generated by the [swagger-codegen](https://github.com/swagger-api/swagger-codegen) project. By using the
[OpenAPI-Spec](https://github.com/swagger-api/swagger-core/wiki) from a remote server, you can easily generate a server stub.  This
is an example of building a swagger-enabled Flask server.

This example uses the [Connexion](https://github.com/zalando/connexion) library on top of Flask.

## Requirements
Python 3.9.6+

## Prerequisite: run the RabbitMQ server
The communication between SDX controller and Local controller rely on RabbitMQ. RabbitMQ can either run on the SDX controller, or run on a separate node. The easiest way to run RabbitMQ is using docker:

```
sudo docker run -it --rm --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:latest
```

Then in `env` and `docker-compose.yml` files, change `MQ_HOST` host to the corresponding IP address or hostname of the RabbitMQ server

## Run with Python
To run the swagger server, please execute the following from the root directory:

```
pip3 install -r requirements.txt
pip3 install "connexion[swagger-ui]"
python3 -m swagger_server
```

and open your browser to here:

```
http://localhost:8080/SDX-Controller/1.0.0/ui/
```

Your Swagger definition lives here:

```
http://localhost:8080/SDX-Controller/1.0.0/swagger.json
```

To launch the integration tests, use tox:
```
sudo pip install tox
tox
```

## Running with Docker (Recommended)

To run the server on a Docker container, execute the following from the root directory:

```bash
# building the image
docker build -t sdx-controller .

# starting up a container
docker run -p 8080:8080 sdx-controller
```

To run the SDX Controller server and BAPM server, Docker is required. 
Execute the following from the root directory:

```bash
# building SDX Controller image
docker build -t sdx-controller .

# build BAPM server image
cd bapm_server
docker build -t bapm-server .

# run both SDX controller and BAPM server with docker-compose
docker-compose up
```

## Communication between SDX Controller and Local Controller

The SDX controller and local controller communicate using RabbitMQ. All the topology and connectivity related messages are sent with RPC, with receiver confirmation. The monitoring related messages are sent without receiver confirmation.

Below are two sample scenarios for RabbitMQ implementation:

SDX controller breaks down the topology and sends connectivity information to local controllers:
![SDX controller to local controller](https://user-images.githubusercontent.com/29924060/139588273-100a0bb2-14ba-496f-aedf-a122b9793325.jpg)

Local controller sends domain information to SDX controller:
![Local controller to SDX controller](https://user-images.githubusercontent.com/29924060/139588283-2ea32803-92e3-4812-9e8a-3d829549ae40.jpg)
