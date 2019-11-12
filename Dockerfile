# Dockerfile for WebVisualizer
ARG EIS_VERSION
FROM ia_eisbase:$EIS_VERSION as eisbase
LABEL description="Web Visualizer image"

ARG HOST_TIME_ZONE=""

WORKDIR ${PY_WORK_DIR}

ARG DEBIAN_FRONTEND=noninteractive
# Setting timezone inside the container
RUN echo "$HOST_TIME_ZONE" >/etc/timezone
RUN cat /etc/timezone
RUN apt-get update && \
    apt-get install -y tzdata && \
    apt-get install -y unzip && \
    ln -sf /usr/share/zoneinfo/${HOST_TIME_ZONE} /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata

COPY requirements.txt .
RUN pip3 install -r requirements.txt

ARG EIS_USER_NAME
RUN adduser --quiet --disabled-password ${EIS_USER_NAME}

RUN touch visualize.log && \
    chown ${EIS_USER_NAME}:${EIS_USER_NAME} visualize.log &&  \
    chmod 777 visualize.log

ENV PYTHONPATH ${PY_WORK_DIR}/

FROM ia_common:$EIS_VERSION as common

FROM eisbase

COPY --from=common ${GO_WORK_DIR}/common/libs ${PY_WORK_DIR}/libs
COPY --from=common ${GO_WORK_DIR}/common/util ${PY_WORK_DIR}/util
COPY --from=common ${GO_WORK_DIR}/common/cmake ${PY_WORK_DIR}/common/cmake
COPY --from=common /usr/local/lib /usr/local/lib
COPY --from=common /usr/local/lib/python3.6/dist-packages/ /usr/local/lib/python3.6/dist-packages

COPY webVisualizer.py .

RUN mkdir static

RUN wget https://github.com/twbs/bootstrap/releases/download/v4.0.0/bootstrap-4.0.0-dist.zip
RUN unzip bootstrap-4.0.0-dist.zip -d static

RUN wget https://code.jquery.com/jquery-3.4.1.min.js
RUN cp jquery-3.4.1.min.js static/js/jquery.min.js

COPY templates templates

RUN apt-get install -y zip

ENTRYPOINT ["python3.6", "webVisualizer.py"]
