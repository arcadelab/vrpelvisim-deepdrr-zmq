# PelvisVR Server

[![Docker](https://github.com/arcadelab/pelvisvr-deepdrr-zmq/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/arcadelab/pelvisvr-deepdrr-zmq/actions/workflows/docker-publish.yml)

<!-- [![Docker](https://github.com/PelvisVR/deepdrr_zmq/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/PelvisVR/deepdrr_zmq/actions/workflows/docker-publish.yml) -->

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

## Installation

- Install Docker
  - If on windows, don't use docker desktop 4.17.1 <https://github.com/docker/for-win/issues/13324>
- Create a .env file in the root directory of this repository with the following contents:

```
# .env
DOCKER_PATIENT_DATA_DIR="C:\path\to\patient\data"
DOCKER_LOG_DIR="D:/pvrlogs/"
```

- cd to the root directory of this repository
- `docker pull ghcr.io/pelvisvr/deepdrr_zmq:master`
- `docker compose up -d --no-build`

## Documentation

- [API](https://pelvisvr.github.io/deepdrr_zmq/deepdrrzmq.html)
