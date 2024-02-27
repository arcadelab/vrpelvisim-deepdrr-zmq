# syntax=docker/dockerfile:1
   
FROM pytorch/pytorch:1.13.1-cuda11.6-cudnn8-runtime as base

RUN apt-get update --fix-missing && \
    DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC apt-get -y install tzdata && \
    apt-get install -y --no-install-recommends \
    bzip2 \
    build-essential \
    ca-certificates \
    curl \
    ffmpeg \
    freeglut3-dev \
    git \
    libegl1 \
    libegl1-mesa-dev \
    libgles2 \
    libgles2-mesa-dev \
    libgl1 \
    libgl1-mesa-dev \
    libglvnd-dev \
    libglvnd0 \
    libglx0 \
    libsm6 \
    libxext6 \
    pkg-config \
    wget && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Add NVIDIA drivers to glvnd
RUN mkdir -p /usr/share/glvnd/egl_vendor.d/ && \
    echo "{\n\
    \"file_format_version\" : \"1.0.0\",\n\
    \"ICD\": {\n\
    \"library_path\": \"libEGL_nvidia.so.0\"\n\
    }\n\
    }" > /usr/share/glvnd/egl_vendor.d/10_nvidia.json

WORKDIR /app

# Install conda dependencies
# RUN conda install -c conda-forge pycuda -y

# Install deepdrr and pip dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# CMD python deepdrrzmq.maanager
CMD ["python", "-m", "deepdrrzmq.manager"]

# Expose ports
EXPOSE 40120/tcp
EXPOSE 40121/tcp
EXPOSE 40122/tcp
