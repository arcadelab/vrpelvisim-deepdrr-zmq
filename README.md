# PelvisVR Server

[![Docker](https://github.com/arcadelab/vrpelvisim-deepdrr-zmq/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/arcadelab/vrpelvisim-deepdrr-zmq/actions/workflows/docker-publish.yml)

<!-- ZMQ/Capnp interface for [DeepDRR](https://github.com/arcadelab/deepdrr). -->

Server docker container for the PelvisVR percutaneous pelvic surgery simulator.

The PelvisVR client is located [here](https://git.lcsr.jhu.edu/pelvisvr/vr_surgical_room).

The server is responsible for:

- Loading patient mesh and annotation data (patientloaderd.py)
- Generating DeepDRR projections (deepdrrd.py)
- Providing a global time reference (timed.py)
- Logging all user interactions and collected DeepDRR projections for future analysis (loggerd.py)

## Requirements

- Computer running Windows or Linux and GPU with CUDA support and >11GB of VRAM

## Installing Docker

Please follow the [official Docker installation guide](https://docs.docker.com/desktop/) based on your operating system:

- [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/)
  - **Note**: Avoid using Docker Desktop version 4.17.1 due to known issues. Refer to [this issue](https://github.com/docker/for-win/issues/13324) for details.
- [Docker Desktop for Linux](https://docs.docker.com/desktop/install/linux-install/)

## Setting Up the Environment

Open your terminal or command prompt and navigate to the root directory of the `vrpelvisim-deepdrr-zmq` repository.

1. Create a `.env` file in the root directory:
    ```bash
    touch .env
    ```
2. Open the `.env` file and add the following environment variables:
    ```bash
    # .env
    DOCKER_PATIENT_DATA_DIR="C:/path/to/patient/data"
    DOCKER_LOG_DIR="C:/path/to/logs/"
    ```

## Running the Application

Open your terminal or command prompt and navigate to the root directory of the `vrpelvisim-deepdrr-zmq` repository.

1. Pull the latest Docker image for the `vrpelvisim-deepdrr-zmq` application:
    ```bash
    docker pull ghcr.io/arcadelab/vrpelvisim-deepdrr-zmq:main
    ```
2. Start the application using Docker Compose:
    ```bash
    docker compose up -d --no-build
    ```

## Documentation

- [API](https://pelvisvr.github.io/deepdrr_zmq/deepdrrzmq.html)
