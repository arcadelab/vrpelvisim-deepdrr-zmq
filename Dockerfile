# syntax=docker/dockerfile:1
   
FROM pytorch/pytorch:1.13.1-cuda11.6-cudnn8-runtime as base
WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    build-essential \
    git
    # && rm -rf /var/lib/apt/lists/*

# RUN apt-get update && apt-get install ffmpeg libsm6 libxext6 build-essential git -y

RUN conda install -c conda-forge pycuda -y
    # && conda clean -a -y

# RUN conda install -c conda-forge pycuda -y

COPY requirements.txt .
RUN pip install -r requirements.txt
    # && rm -rf /root/.cache/pip
# RUN pip install -r requirements.txt

COPY . .

CMD ["python", "-m", "deepdrrzmq.manager"]

EXPOSE 40100/tcp
EXPOSE 40101/tcp
EXPOSE 40102/tcp