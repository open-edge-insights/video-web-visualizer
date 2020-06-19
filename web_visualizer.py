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
from eis.config_manager import ConfigManager
from eis.env_config import EnvConfig
import eis.msgbus as mb
import cv2
from jinja2 import Environment, select_autoescape, FileSystemLoader
import numpy as np
from flask import Flask, render_template, Response, request, session
from util.util import Util
from util.log import configure_logging


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


class SubscriberCallback:
    """Object for the databus callback to wrap needed state variables for the
    callback in to EIS.
    """
    def __init__(self, topic_queue_dict, logger, good_color=(0, 255, 0),
                 bad_color=(0, 0, 255), labels=None):
        """Constructor

        :param topic_queue_dict: Dictionary to maintain multiple queues.
        :type: dict
        :param labels: (Optional) Label mapping for text to draw on the frame
        :type: dict
        :param good_color: (Optional) Tuple for RGB color to use for outlining
            a good image
        :type: tuple
        :param bad_color: (Optional) Tuple for RGB color to use for outlining a
            bad image
        :type: tuple
        """
        self.topic_queue_dict = topic_queue_dict
        self.logger = logger
        self.good_color = good_color
        self.bad_color = bad_color
        self.labels = labels
        self.msg_frame_queue = queue.Queue(maxsize=15)

    def queue_publish(self, topic, frame):
        """queue_publish called after defects bounding box is drawn
        on the image. These images are published over the queue.

        :param topic: Topic the message was published on
        :type: str
        :param frame: Images with the bounding box
        :type: numpy.ndarray
        """
        for key in self.topic_queue_dict:
            if key == topic:
                if not self.topic_queue_dict[key].full():
                    self.topic_queue_dict[key].put_nowait(frame)
                    del frame
                else:
                    self.logger.debug("Dropping frames as the queue is full")

    def draw_defect(self, results, blob, stream_label=None):
        """Identify the defects and draw boxes on the frames

        :param results: Metadata of frame received from message bus.
        :type: dict
        :param blob: Actual frame received from message bus.
        :type: bytes
        :param results: Message received on the given topic (JSON blob)
        :type: str
        :return: Return classified results(metadata and frame)
        :rtype: dict and numpy array
        """
        height = int(results['height'])
        width = int(results['width'])
        channels = int(results['channels'])
        encoding = None

        if 'encoding_type' and 'encoding_level' in results:
            encoding = {"type": results['encoding_type'],
                        "level": results['encoding_level']}
        # Convert to Numpy array and reshape to frame
        self.logger.debug('Preparing frame for visualization')
        frame = np.frombuffer(blob, dtype=np.uint8)
        if encoding is not None:
            frame = np.reshape(frame, (frame.shape))
            try:
                frame = cv2.imdecode(frame, 1)
            except cv2.error as ex:
                self.logger.error("frame: {}, exception: {}".format(frame, ex))
        else:
            self.logger.debug("Encoding not enabled...")
            frame = np.reshape(frame, (height, width, channels))

        # Draw defects for Gva
        if 'gva_meta' in results:
            count = 0
            for defect in results['gva_meta']:
                x_1 = defect['x']
                y_1 = defect['y']
                x_2 = x_1 + defect['width']
                y_2 = y_1 + defect['height']

                top_left = tuple([x_1, y_1])
                bottom_right = tuple([x_2, y_2])

                # Draw bounding box
                cv2.rectangle(frame, top_left, bottom_right, self.bad_color, 2)

                # Draw labels
                for label_list in defect['tensor']:
                    if label_list['label_id'] is not None:
                        pos = (x_1, y_1 - count)
                        count += 10
                        if stream_label is not None and \
                           str(label_list['label_id']) in stream_label:
                            label = stream_label[str(label_list['label_id'])]
                            cv2.putText(frame, label, pos,
                                        cv2.FONT_HERSHEY_DUPLEX,
                                        0.5, self.bad_color, 2,
                                        cv2.LINE_AA)
                        else:
                            self.logger.error("Label id:{}\
                                              not found".format(
                                                  label_list['label_id']))

        # Draw defects
        if 'defects' in results:
            for defect in results['defects']:
                defect['tl'][0] = int(defect['tl'][0])
                defect['tl'][1] = int(defect['tl'][1])
                defect['br'][0] = int(defect['br'][0])
                defect['br'][1] = int(defect['br'][1])

                # Get tuples for top-left and bottom-right coordinates
                top_left = tuple(defect['tl'])
                bottom_right = tuple(defect['br'])

                # Draw bounding box
                cv2.rectangle(frame, top_left, bottom_right, self.bad_color, 2)

                # Draw labels for defects if given the mapping
                if stream_label is not None:
                    # Position of the text below the bounding box
                    pos = (top_left[0], bottom_right[1] + 20)

                    # The label is the "type" key of the defect, which
                    #  is converted to a string for getting from the labels
                    if str(defect['type']) in stream_label:
                        label = stream_label[str(defect['type'])]
                        cv2.putText(frame, label, pos,
                                    cv2.FONT_HERSHEY_DUPLEX,
                                    0.5, self.bad_color, 2, cv2.LINE_AA)
                    else:
                        cv2.putText(frame, str(defect['type']), pos,
                                    cv2.FONT_HERSHEY_DUPLEX,
                                    0.5, self.bad_color, 2, cv2.LINE_AA)

            # Draw border around frame if has defects or no defects
            if results['defects']:
                outline_color = self.bad_color
            else:
                outline_color = self.good_color

            frame = cv2.copyMakeBorder(frame, 5, 5, 5, 5, cv2.BORDER_CONSTANT,
                                       value=outline_color)

        # Display information about frame FPS
        x_cord = 20
        y_cord = 20
        for res in results:
            if "Fps" in res:
                fps_str = "{} : {}".format(str(res), str(results[res]))
                self.logger.info(fps_str)
                cv2.putText(frame, fps_str, (x_cord, y_cord),
                            cv2.FONT_HERSHEY_DUPLEX, 0.5,
                            self.good_color, 1, cv2.LINE_AA)
                y_cord = y_cord + 20

        # Display information about frame
        (d_x, d_y) = (20, 50)
        if 'display_info' in results:
            for d_i in results['display_info']:
                # Get priority
                priority = d_i['priority']
                info = d_i['info']
                d_y = d_y + 10

                #  LOW
                if priority == 0:
                    cv2.putText(frame, info, (d_x, d_y),
                                cv2.FONT_HERSHEY_DUPLEX,
                                0.5, (0, 255, 0), 1, cv2.LINE_AA)
                #  MEDIUM
                if priority == 1:
                    cv2.putText(frame, info, (d_x, d_y),
                                cv2.FONT_HERSHEY_DUPLEX,
                                0.5, (0, 150, 170), 1, cv2.LINE_AA)
                #  HIGH
                if priority == 2:
                    cv2.putText(frame, info, (d_x, d_y),
                                cv2.FONT_HERSHEY_DUPLEX,
                                0.5, (0, 0, 255), 1, cv2.LINE_AA)

        return results, frame

    def callback(self, msgbus_cfg, topic):
        """Callback called when the databus has a new message.

        :param msgbus_cfg: config for the context creation in EISMessagebus
        :type: str
        :param topic: Topic the message was published on
        :type: str
        """
        self.logger.debug('Initializing message bus context')

        msgbus = mb.MsgbusContext(msgbus_cfg)

        self.logger.debug(f'Initializing subscriber for topic \'{topic}\'')
        subscriber = msgbus.new_subscriber(topic)

        stream_label = None

        for key in self.labels:
            if key == topic:
                stream_label = self.labels[key]
                break

        while True:
            metadata, blob = subscriber.recv()

            if metadata is not None and blob is not None:
                results, frame = self.draw_defect(metadata, blob,
                                                  stream_label)

                del results
                self.queue_publish(topic, frame)
            else:
                self.logger.debug(f'Non Image Data Subscription\
                                 : Classifier_results: {metadata}')


def msg_bus_subscriber(topic_config_list, queue_dict, logger, json_config):
    """msg_bus_subscriber is the ZeroMQ callback to
    subscribe to classified results
    """
    sub_cbk = SubscriberCallback(queue_dict, logger,
                                 labels=json_config["labels"])

    for topic_config in topic_config_list:
        topic, msgbus_cfg = topic_config

        callback_thread = threading.Thread(target=sub_cbk.callback,
                                           args=(msgbus_cfg, topic, ))
        callback_thread.start()


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
    dev_mode = bool(strtobool(os.environ["DEV_MODE"]))
    # Initializing Etcd to set env variables

    app_name = os.environ["AppName"]
    conf = Util.get_crypto_dict(app_name)

    cfg_mgr = ConfigManager()
    config_client = cfg_mgr.get_config_client("etcd", conf)

    global_env_config = config_client.GetConfig("/GlobalEnv/")
    global_config = json.loads(global_env_config)
    logger = configure_logging(global_config['PY_LOG_LEVEL'].upper(),
                               __name__, dev_mode)

    visualizer_config = config_client.GetConfig("/" + app_name + "/config")
    json_config = json.loads(visualizer_config)

    topics_list = EnvConfig.get_topics_from_env("sub")
    queue_dict = {}
    topics_list = EnvConfig.get_topics_from_env("sub")

    sub_dict = {}
    for subtopic in topics_list:
        publisher, topic = subtopic.split("/")
        sub_dict[topic] = publisher

    topic_config_list = []
    queue_dict[topic_name] = queue.Queue(maxsize=10)
    msgbus_cfg = EnvConfig.get_messagebus_config(topic_name,
                                                 "sub", sub_dict[topic_name],
                                                 config_client, dev_mode)

    mode_address = os.environ[topic_name + "_cfg"].split(",")
    mode = mode_address[0].strip()
    if (not dev_mode and mode == "zmq_tcp"):
        for key in msgbus_cfg[topic_name]:
            if msgbus_cfg[topic_name][key] is None:
                raise ValueError("Invalid Config")

    topic_config = (topic_name, msgbus_cfg)
    topic_config_list.append(topic_config)
    try:
        final_image = get_blank_image(TEXT)
        msg_bus_subscriber(topic_config_list, queue_dict, logger,
                           json_config)
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


def get_topic_list():
    """Get list of topics
    """
    topics_list = EnvConfig.get_topics_from_env("sub")
    final_topic_list = []
    for topic in topics_list:
        _, topic = topic.split("/")
        topic = topic.strip()
        final_topic_list.append(topic)
    return final_topic_list


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
    dev_mode = bool(strtobool(os.environ["DEV_MODE"]))
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

    return Response(str(get_topic_list()))


@APP.route('/<topic_name>', methods=['GET'])
def render_image(topic_name):
    """Renders images over http
    """
    if topic_name in get_topic_list():
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
        app_name = os.environ["AppName"]
        conf = Util.get_crypto_dict(app_name)
        cfg_mgr = ConfigManager()
        config_client = cfg_mgr.get_config_client("etcd", conf)
        visualizer_config = config_client.GetConfig("/" + app_name + "/config")

        json_config = json.loads(visualizer_config)
        dev_mode = bool(strtobool(os.environ["DEV_MODE"]))
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
    dev_mode = bool(strtobool(os.environ["DEV_MODE"]))
    if not dev_mode:
        session['logged_in'] = False
    return login()


def main():
    """Main Method for WebVisualizer App
    """

    APP.secret_key = os.urandom(24)
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    dev_mode = bool(strtobool(os.environ["DEV_MODE"]))
    app_name = os.environ["AppName"]
    conf = Util.get_crypto_dict(app_name)
    cfg_mgr = ConfigManager()
    config_client = cfg_mgr.get_config_client("etcd", conf)
    visualizer_config = config_client.GetConfig("/" + app_name + "/config")

    # Validating config against schema
    with open('./schema.json', "rb") as infile:
        schema = infile.read()
        if (Util.validate_json(schema, visualizer_config)) is not True:
            sys.exit(1)

    json_config = json.loads(visualizer_config)

    global_env_config = config_client.GetConfig("/GlobalEnv/")
    global_config = json.loads(global_env_config)

    flask_debug = bool(global_config['PY_LOG_LEVEL'].lower() == 'debug')

    if dev_mode:
        APP.run(host='0.0.0.0', port=json_config['port'],
                debug=flask_debug, threaded=True)
    else:
        # For Secure Session Cookie
        APP.config.update(SESSION_COOKIE_SECURE=True)
        server_cert = config_client.GetConfig("/" + app_name + "/server_cert")
        server_key = config_client.GetConfig("/" + app_name + "/server_key")

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
        APP.run(host='0.0.0.0', port=json_config['port'],
                debug=flask_debug, threaded=True, ssl_context=context)


if __name__ == '__main__':
    main()
