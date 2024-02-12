# syntax=docker/dockerfile:1
   
FROM pytorch/pytorch:1.13.1-cuda11.6-cudnn8-runtime as base
WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    build-essential \
    git

RUN conda install -c conda-forge pycuda -y

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "-m", "deepdrrzmq.manager"]

EXPOSE 40120/tcp
EXPOSE 40121/tcp
EXPOSE 40122/tcp