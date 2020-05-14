# Dockerfile for WebVisualizer
ARG EIS_VERSION
ARG DOCKER_REGISTRY
FROM ${DOCKER_REGISTRY}ia_eisbase:$EIS_VERSION as eisbase
LABEL description="Web Visualizer Image"

WORKDIR ${PY_WORK_DIR}

RUN apt-get update && \
    apt-get install -y unzip && \
    mkdir static && \
    wget https://github.com/twbs/bootstrap/releases/download/v4.0.0/bootstrap-4.0.0-dist.zip && \
    unzip bootstrap-4.0.0-dist.zip -d static && \
    wget https://code.jquery.com/jquery-3.4.1.min.js && \
    cp jquery-3.4.1.min.js static/js/jquery.min.js

COPY requirements.txt .
RUN pip3 install -r requirements.txt

ARG EIS_USER_NAME
RUN adduser --quiet --disabled-password ${EIS_USER_NAME}

ENV PYTHONPATH ${PY_WORK_DIR}/

FROM ${DOCKER_REGISTRY}ia_common:$EIS_VERSION as common

FROM eisbase

COPY --from=common ${GO_WORK_DIR}/common/libs ${PY_WORK_DIR}/libs
COPY --from=common ${GO_WORK_DIR}/common/util ${PY_WORK_DIR}/util
COPY --from=common ${GO_WORK_DIR}/common/cmake ${PY_WORK_DIR}/common/cmake
COPY --from=common /usr/local/lib /usr/local/lib
COPY --from=common /usr/local/lib/python3.6/dist-packages/ /usr/local/lib/python3.6/dist-packages

COPY . .

ENTRYPOINT ["python3.6", "web_visualizer.py"]
