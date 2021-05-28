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

"""Simple visualizer for images processed by ETA.
"""
import os
import time
import sys
import json
import queue
from distutils.util import strtobool
import threading
import random
import ssl
import secrets
import tempfile
import eii.msgbus as mb
import cv2
from jinja2 import Environment, select_autoescape, FileSystemLoader
import numpy as np
from flask import Flask, render_template, Response, request, session
from util.util import Util
from util.log import configure_logging
import cfgmgr.config_manager as cfg
from util.common import Visualizer

TEXT = 'Disconnected'
TEXTPOSITION = (10, 110)
TEXTFONT = cv2.FONT_HERSHEY_PLAIN
TEXTCOLOR = (255, 255, 255)
MAX_FAILED_LOGIN_ATTEMPTS = 3
NUMBER_OF_LOGIN_ATTEMPTS = 0

NONCE = secrets.token_urlsafe(8)
APP = Flask(__name__)
LOADER = FileSystemLoader(searchpath="templates/")

# Setting default auto-escape for all templates
ENV = Environment(loader=LOADER, autoescape=select_autoescape(
    enabled_extensions=('html'),
    default_for_string=True,))

# Config manager initialization
ctx = cfg.ConfigMgr()
queue_dict = {}
topic_config_list = []
topics_list = []


def msg_bus_subscriber(topic_name, logger, json_config):
    """msg_bus_subscriber is the ZeroMQ callback to
    subscribe to classified results
    """
    visualizer = Visualizer(queue_dict, logger,
                            labels=json_config["labels"],
                            draw_results=json_config["draw_results"])

    for topic_config in topic_config_list:

        topic, msgbus_cfg = topic_config

        if topic_name == topic:
            callback_thread = threading.Thread(target=visualizer.callback,
                                               args=(msgbus_cfg, topic, ))
            callback_thread.start()
            break


def get_blank_image(text):
    """Get Blank Images
    """
    blank_image_shape = (130, 200, 3)
    blank_image = np.zeros(blank_image_shape, dtype=np.uint8)
    cv2.putText(blank_image, text, TEXTPOSITION,
                TEXTFONT, 1.5, TEXTCOLOR, 2, cv2.LINE_AA)
    _, jpeg = cv2.imencode('.jpg', blank_image)
    final_image = jpeg.tobytes()
    return final_image


def get_image_data(topic_name):
    """Get the Images from Zmq
    """
    dev_mode = ctx.is_dev_mode()
    # Initializing Etcd to set env variables

    logger = configure_logging(os.environ['PY_LOG_LEVEL'].upper(),
                               __name__, dev_mode)

    json_config = ctx.get_app_config()
    try:
        final_image = get_blank_image(TEXT)
        msg_bus_subscriber(topic_name, logger, json_config)
        while True:
            if topic_name in queue_dict.keys():
                if not queue_dict[topic_name].empty():
                    frame = queue_dict[topic_name].get_nowait()
                    ret, jpeg = cv2.imencode('.jpg', frame)
                    del frame
                    final_image = jpeg.tobytes()
                    del jpeg
            else:
                msg_txt = "Topic Not Found: " + topic_name
                final_image = get_blank_image(msg_txt)

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + final_image +
                   b'\r\n\r\n')
    except KeyboardInterrupt:
        logger.info('Quitting...')
    except Exception:
        logger.exception('Error during execution:')


def assert_exists(path):
    """Assert given path exists.

    :param path: Path to assert
    :type: str
    """
    assert os.path.exists(path), 'Path: {} does not exist'.format(path)


def set_header_tags(response):
    """Local function to set secure response tags"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000;\
                                                    includeSubDomains'
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    return response


@APP.route('/')
def index():
    """Video streaming home page."""
    dev_mode = ctx.is_dev_mode()
    if not session.get('logged_in'):
        if dev_mode:
            session['logged_in'] = True
            response = APP.make_response(render_template('index.html',
                                                         nonce=NONCE))
            return set_header_tags(response)
        response = APP.make_response(render_template('login.html',
                                                     nonce=NONCE))
        return set_header_tags(response)

    response = APP.make_response(render_template('index.html',
                                                 nonce=NONCE))
    return set_header_tags(response)


@APP.route('/topics', methods=['GET'])
def return_topics():
    """Returns topics list over http
    """
    if not session.get('logged_in'):
        response = APP.make_response(render_template('login.html',
                                                     nonce=NONCE))
        return set_header_tags(response)

    return Response(str(topics_list))


@APP.route('/<topic_name>', methods=['GET'])
def render_image(topic_name):
    """Renders images over http
    """
    if topic_name in topics_list:
        if not session.get('logged_in'):
            response = APP.make_response(render_template('login.html',
                                                         nonce=NONCE))
            return set_header_tags(response)

        return Response(get_image_data(topic_name),
                        mimetype='multipart/x-mixed-replace;\
                                  boundary=frame')

    return Response("Invalid Request")


@APP.route('/login', methods=['GET', 'POST'])
def login():
    """The main login page for WebVisualizer
    """
    assert len(request.url) < 2000, "Request URL size exceeds browser limit"
    if request.method == 'GET':
        if not session.get('logged_in'):
            response = APP.make_response(render_template('login.html',
                                                         nonce=NONCE))
            return set_header_tags(response)

        return index()

    if request.method == 'POST':
        json_config = ctx.get_app_config()
        dev_mode = ctx.is_dev_mode()
        # global MAX_FAILED_LOGIN_ATTEMPTS
        global NUMBER_OF_LOGIN_ATTEMPTS
        if dev_mode:
            session['logged_in'] = True
        else:
            if request.form['username'] == json_config['username'] \
               and request.form['password'] == json_config['password']:
                session['logged_in'] = True
                NUMBER_OF_LOGIN_ATTEMPTS = 0
                return index()

            response = APP.make_response(render_template('login.html',
                                                         nonce=NONCE,
                                                         Message="Invalid\
                                                            Login"))
            NUMBER_OF_LOGIN_ATTEMPTS += 1
            if NUMBER_OF_LOGIN_ATTEMPTS == MAX_FAILED_LOGIN_ATTEMPTS:
                response = APP.make_response(render_template('login.html',
                                                             nonce=NONCE,
                                                             Message="\
                                                                Invalid\
                                                                Login. Retry\
                                                                after a while\
                                                                ."))
                time.sleep(random.randint(3, 10))
                NUMBER_OF_LOGIN_ATTEMPTS = 0
            # Random sleep between 0.1 to 0.5secs on InvalidLogin response.
            # SDLE
            time.sleep(random.uniform(0.1, 0.5))
            return set_header_tags(response)
    else:
        return Response("Only GET and POST methods are supported.")
    return index()


@APP.route('/logout', methods=['GET'])
def logout():
    """Logout page for WebVisualizer
    """
    dev_mode = ctx.is_dev_mode()
    if not dev_mode:
        session['logged_in'] = False
    return login()


def main():
    """Main Method for WebVisualizer App
    """
    APP.secret_key = os.urandom(24)
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    dev_mode = ctx.is_dev_mode()

    json_config = ctx.get_app_config()

    # Validating config against schema
    with open('./schema.json', "rb") as infile:
        schema = infile.read()
        if not (Util.validate_json(schema,
                                   json.dumps(json_config.get_dict()))):
            sys.exit(1)

    num_of_subscribers = ctx.get_num_subscribers()
    for index in range(num_of_subscribers):
        # Fetching subscriber element based on index
        sub_ctx = ctx.get_subscriber_by_index(index)
        # Fetching msgbus config of subscriber
        msgbus_cfg = sub_ctx.get_msgbus_config()
        # Fetching topics of subscriber
        topic = sub_ctx.get_topics()[0]
        # Adding topic & msgbus_config to
        # topic_config tuple
        topic_config = (topic, msgbus_cfg)
        topic_config_list.append(topic_config)
        topics_list.append(topic)
        queue_dict[topic] = queue.Queue(maxsize=10)

    flask_debug = bool(os.environ['PY_LOG_LEVEL'].lower() == 'debug')

    if dev_mode:

        APP.run(host='0.0.0.0', port=json_config['dev_port'],
                debug=flask_debug, threaded=True)
    else:
        # For Secure Session Cookie
        APP.config.update(SESSION_COOKIE_SECURE=True,
                          SESSION_COOKIE_SAMESITE='Lax')

        server_cert = json_config["server_cert"]
        server_key = json_config["server_key"]

        # Since Python SSL Load Cert Chain Method is not having option to load
        # Cert from Variable. So for now we are going below method
        server_cert_temp = tempfile.NamedTemporaryFile()
        server_key_temp = tempfile.NamedTemporaryFile()

        server_cert_temp.write(bytes(server_cert, "utf-8"))
        server_cert_temp.seek(0)

        server_key_temp.write(bytes(server_key, "utf-8"))
        server_key_temp.seek(0)

        context.load_cert_chain(server_cert_temp.name, server_key_temp.name)
        server_cert_temp.close()
        server_key_temp.close()
        APP.run(host='0.0.0.0', port=json_config['port'], # nosec
                debug=flask_debug, threaded=True, ssl_context=context)


if __name__ == '__main__':
    main()
