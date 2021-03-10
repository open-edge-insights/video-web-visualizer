# Copyright (c) 2020 Intel Corporation.

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# Dockerfile for WebVisualizer

ARG EII_VERSION
ARG DOCKER_REGISTRY
FROM ${DOCKER_REGISTRY}ia_eiibase:$EII_VERSION as eiibase
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

ARG EII_USER_NAME
RUN adduser --quiet --disabled-password ${EII_USER_NAME}

ENV PYTHONPATH ${PY_WORK_DIR}/

FROM ${DOCKER_REGISTRY}ia_common:$EII_VERSION as common

FROM eiibase

COPY --from=common ${GO_WORK_DIR}/common/libs ${PY_WORK_DIR}/libs
COPY --from=common ${GO_WORK_DIR}/common/util ${PY_WORK_DIR}/util
COPY --from=common ${GO_WORK_DIR}/common/cmake ${PY_WORK_DIR}/common/cmake
COPY --from=common /usr/local/lib /usr/local/lib
COPY --from=common /usr/local/lib/python3.6/dist-packages/ /usr/local/lib/python3.6/dist-packages


COPY . .

HEALTHCHECK NONE

ENTRYPOINT ["python3.6", "web_visualizer.py"]
