"""Simple visualizer for images processed by ETA.
"""
import io
import os
import time
import sys
import cv2
import json
import queue
import logging
import argparse
import numpy as np
from distutils.util import strtobool
import threading
import time
import random
from libs.ConfigManager import ConfigManager
from util.util import Util
from util.msgbusutil import MsgBusUtil
import eis.msgbus as mb
from util.log import configure_logging, LOG_LEVELS
from flask import Flask, render_template, Response, redirect, request, \
                         session, abort, escape
from jinja2 import Environment, select_autoescape, FileSystemLoader
import ssl
import string
import secrets
import tempfile

TEXT = 'Disconnected'
TEXTPOSITION = (10, 110)
TEXTFONT = cv2.FONT_HERSHEY_PLAIN
TEXTCOLOR = (255, 255, 255)
MAX_FAILED_LOGIN_ATTEMPTS = 3
number_of_login_attempts = 0

NONCE = secrets.token_urlsafe(8)
app = Flask(__name__)
loader = FileSystemLoader(searchpath="templates/")

# Setting default auto-escape for all templates
env = Environment(loader=loader, autoescape=select_autoescape(
                  enabled_extensions=('html'),
                  default_for_string=True,))


class SubscriberCallback:
    """Object for the databus callback to wrap needed state variables for the
    callback in to EIS.
    """
    def __init__(self, topicQueueDict, logger, good_color=(0, 255, 0),
                 bad_color=(0, 0, 255), display=None,
                 labels=None):
        """Constructor

        :param frame_queue: Queue to put frames in as they become available
        :type: queue.Queue
        :param im_client: Image store client
        :type: GrpcImageStoreClient
        :param labels: (Optional) Label mapping for text to draw on the frame
        :type: dict
        :param good_color: (Optional) Tuple for RGB color to use for outlining
            a good image
        :type: tuple
        :param bad_color: (Optional) Tuple for RGB color to use for outlining a
            bad image
        :type: tuple
        """
        self.topicQueueDict = topicQueueDict
        self.logger = logger
        self.labels = labels
        self.good_color = good_color
        self.bad_color = bad_color
        self.display = display
        self.msg_frame_queue = queue.Queue(maxsize=15)

    def queue_publish(self, topic, frame):
        """queue_publish called after defects bounding box is drawn
        on the image. These images are published over the queue.

        :param topic: Topic the message was published on
        :type: str
        :param frame: Images with the bounding box
        :type: numpy.ndarray
        :param topicQueueDict: Dictionary to maintain multiple queues.
        :type: dict
        """
        for key in self.topicQueueDict:
            if (key == topic):
                if not self.topicQueueDict[key].full():
                    self.topicQueueDict[key].put_nowait(frame)
                    del frame
                else:
                    self.logger.debug("Dropping frames as the queue is full")

    def draw_defect(self, results, blob, topic, stream_label=None):
        """Identify the defects and draw boxes on the frames

        :param results: Metadata of frame received from message bus.
        :type: dict
        :param blob: Actual frame received from message bus.
        :type: bytes
        :param topic: Topic the message was published on
        :type: str
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
            self.logger.info("Encoding not enabled...")
            frame = np.reshape(frame, (height, width, channels))

        # Draw defects for Gva
        if 'gva_meta' in results:
            c = 0
            for d in results['gva_meta']:
                x1 = d['x']
                y1 = d['y']
                x2 = x1 + d['width']
                y2 = y1 + d['height']

                tl = tuple([x1, y1])
                br = tuple([x2, y2])

                # Draw bounding box
                cv2.rectangle(frame, tl, br, self.bad_color, 2)

                # Draw labels
                for l in d['tensor']:
                    if l['label_id'] is not None:
                        pos = (x1, y1 - c)
                        c += 10
                        if stream_label is not None and \
                           str(l['label_id']) in stream_label:
                            label = stream_label[str(l['label_id'])]
                            cv2.putText(frame, label, pos,
                                        cv2.FONT_HERSHEY_DUPLEX,
                                        0.5, self.bad_color, 2,
                                        cv2.LINE_AA)
                        else:
                            self.logger.error("Label id:{}\
                                              not found".format(l['label_id']))

        # Draw defects
        if 'defects' in results:
            for d in results['defects']:
                d['tl'][0] = int(d['tl'][0])
                d['tl'][1] = int(d['tl'][1])
                d['br'][0] = int(d['br'][0])
                d['br'][1] = int(d['br'][1])

                # Get tuples for top-left and bottom-right coordinates
                tl = tuple(d['tl'])
                br = tuple(d['br'])

                # Draw bounding box
                cv2.rectangle(frame, tl, br, self.bad_color, 2)

                # Draw labels for defects if given the mapping
                if stream_label is not None:
                    # Position of the text below the bounding box
                    pos = (tl[0], br[1] + 20)

                    # The label is the "type" key of the defect, which
                    #  is converted to a string for getting from the labels
                    if str(d['type']) in stream_label:
                        label = stream_label[str(d['type'])]
                        cv2.putText(frame, label, pos,
                                    cv2.FONT_HERSHEY_DUPLEX,
                                    0.5, self.bad_color, 2, cv2.LINE_AA)
                    else:
                        cv2.putText(frame, str(d['type']), pos,
                                    cv2.FONT_HERSHEY_DUPLEX,
                                    0.5, self.bad_color, 2, cv2.LINE_AA)

            # Draw border around frame if has defects or no defects
            if results['defects']:
                outline_color = self.bad_color
            else:
                outline_color = self.good_color

            frame = cv2.copyMakeBorder(frame, 5, 5, 5, 5, cv2.BORDER_CONSTANT,
                                       value=outline_color)

        # Display information about frame
        (dx, dy) = (20, 10)
        if 'display_info' in results:
            for d_i in results['display_info']:
                # Get priority
                priority = d_i['priority']
                info = d_i['info']
                dy = dy + 10

                #  LOW
                if priority == 0:
                    cv2.putText(frame, info, (dx, dy), cv2.FONT_HERSHEY_DUPLEX,
                                0.5, (0, 255, 0), 1, cv2.LINE_AA)
                #  MEDIUM
                if priority == 1:
                    cv2.putText(frame, info, (dx, dy), cv2.FONT_HERSHEY_DUPLEX,
                                0.5, (0, 150, 170), 1, cv2.LINE_AA)
                #  HIGH
                if priority == 2:
                    cv2.putText(frame, info, (dx, dy), cv2.FONT_HERSHEY_DUPLEX,
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
                results, frame = self.draw_defect(metadata, blob, topic,
                                                  stream_label)
                if self.display:
                    del results
                    self.queue_publish(topic, frame)
                else:
                    self.logger.info(f'Classifier_results: {results}')
            else:
                self.logger.debug(f'Non Image Data Subscription\
                                 : Classifier_results: {data}')


def parse_args():
    """Parse command line arguments.
    """
    ap = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument('-f', '--fullscreen', default=False, action='store_true',
                    help='Start visualizer in fullscreen mode')
    return ap.parse_args()


def msg_bus_subscriber(topic_config_list, queueDict, logger, jsonConfig):
    """msg_bus_subscriber is the ZeroMQ callback to
    subscribe to classified results
    """
    sc = SubscriberCallback(queueDict, logger,
                            display=True, labels=jsonConfig["labels"])

    for topic_config in topic_config_list:
        topic, msgbus_cfg = topic_config

        callback_thread = threading.Thread(target=sc.callback,
                                           args=(msgbus_cfg, topic, ))
        callback_thread.start()


def get_blank_image(text):
    blankImageShape = (130, 200, 3)
    blankImage = np.zeros(blankImageShape, dtype=np.uint8)
    cv2.putText(blankImage, text, TEXTPOSITION,
                TEXTFONT, 1.5, TEXTCOLOR, 2, cv2.LINE_AA)
    ret, jpeg = cv2.imencode('.jpg', blankImage)
    finalImage = jpeg.tobytes()
    return finalImage


def get_image_data(topic_name):
    """Get the Images from Zmq
    """
    dev_mode = bool(strtobool(os.environ["DEV_MODE"]))
    # Initializing Etcd to set env variables

    app_name = os.environ["AppName"]
    conf = Util.get_crypto_dict(app_name)

    cfg_mgr = ConfigManager()
    config_client = cfg_mgr.get_config_client("etcd", conf)

    globalenvConfig = config_client.GetConfig("/GlobalEnv/")
    globalConfig = json.loads(globalenvConfig)
    logger = configure_logging(globalConfig['PY_LOG_LEVEL'].upper(),
                               __name__, dev_mode)

    visualizerConfig = config_client.GetConfig("/" + app_name + "/config")
    jsonConfig = json.loads(visualizerConfig)

    topicsList = MsgBusUtil.get_topics_from_env("sub")
    queueDict = {}
    topicsList = MsgBusUtil.get_topics_from_env("sub")

    subDict = {}
    for subtopic in topicsList:
        publisher, topic = subtopic.split("/")
        subDict[topic] = publisher

    topic_config_list = []
    queueDict[topic_name] = queue.Queue(maxsize=10)
    msgbus_cfg = MsgBusUtil.get_messagebus_config(topic_name,
                                                  "sub", subDict[topic_name],
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
        finalImage = get_blank_image(TEXT)
        msg_bus_subscriber(topic_config_list, queueDict, logger,
                           jsonConfig)
        while True:
            if topic_name in queueDict.keys():
                if not queueDict[topic_name].empty():
                    frame = queueDict[topic_name].get_nowait()
                    ret, jpeg = cv2.imencode('.jpg', frame)
                    del frame
                    finalImage = jpeg.tobytes()
                    del jpeg
            else:
                msg_txt = "Topic Not Found: " + topic_name
                finalImage = get_blank_image(msg_txt)

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + finalImage +
                   b'\r\n\r\n')
    except KeyboardInterrupt:
        logger.info('Quitting...')
    except Exception:
        logger.exception('Error during execution:')


def get_topic_list():
    topicsList = MsgBusUtil.get_topics_from_env("sub")
    finaltopicList = []
    for topic in topicsList:
        publisher, topic = topic.split("/")
        topic = topic.strip()
        finaltopicList.append(topic)
    return finaltopicList


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


@app.route('/')
def index():
    dev_mode = bool(strtobool(os.environ["DEV_MODE"]))
    """Video streaming home page."""
    if not session.get('logged_in'):
        if dev_mode:
            session['logged_in'] = True
            response = app.make_response(render_template('index.html',
                                                         nonce=NONCE))
            return set_header_tags(response)
        else:
            response = app.make_response(render_template('login.html',
                                                         nonce=NONCE))
            return set_header_tags(response)
    else:
        response = app.make_response(render_template('index.html',
                                                     nonce=NONCE))
        return set_header_tags(response)


@app.route('/topics', methods=['GET'])
def return_topics():
    if not session.get('logged_in'):
        response = app.make_response(render_template('login.html',
                                                     nonce=NONCE))
        return set_header_tags(response)
    else:
        return Response(str(get_topic_list()))


@app.route('/<topic_name>', methods=['GET'])
def render_image(topic_name):
    if topic_name in get_topic_list():
        if not session.get('logged_in'):
            response = app.make_response(render_template('login.html',
                                                         nonce=NONCE))
            return set_header_tags(response)
        else:
            return Response(get_image_data(topic_name),
                            mimetype='multipart/x-mixed-replace;\
                                      boundary=frame')
    else:
        return Response("Invalid Request")


@app.route('/login', methods=['GET', 'POST'])
def login():
    assert len(request.url) < 2000, "Request URL size exceeds browser limit"
    if request.method == 'GET':
        if not session.get('logged_in'):
            response = app.make_response(render_template('login.html',
                                                         nonce=NONCE))
            return set_header_tags(response)
        else:
            return index()

    elif request.method == 'POST':
        app_name = os.environ["AppName"]
        conf = Util.get_crypto_dict(app_name)
        cfg_mgr = ConfigManager()
        config_client = cfg_mgr.get_config_client("etcd", conf)
        visualizerConfig = config_client.GetConfig("/" + app_name + "/config")

        jsonConfig = json.loads(visualizerConfig)
        dev_mode = bool(strtobool(os.environ["DEV_MODE"]))
        # global MAX_FAILED_LOGIN_ATTEMPTS
        global number_of_login_attempts
        if dev_mode:
            session['logged_in'] = True
        else:
            if request.form['username'] == jsonConfig['username'] \
               and request.form['password'] == jsonConfig['password']:
                session['logged_in'] = True
                number_of_login_attempts = 0
                return index()
            else:
                response = app.make_response(render_template('login.html',
                                                             nonce=NONCE,
                                                             Message="Invalid\
                                                             Login"))
                number_of_login_attempts += 1
                if(number_of_login_attempts == MAX_FAILED_LOGIN_ATTEMPTS):
                    response = app.make_response(render_template('login.html',
                                                                 nonce=NONCE,
                                                                 Message="\
                                                                 Invalid\
                                                                 Login. Retry\
                                                                 after a while\
                                                                 ."))
                    time.sleep(random.randint(3, 10))
                    number_of_login_attempts = 0
                # Random sleep between 0.1 to 0.5secs on InvalidLogin response.
                # SDLE
                time.sleep(random.uniform(0.1, 0.5))
                return set_header_tags(response)
    else:
        return Response("Only GET and POST methods are supported.")
    return index()


@app.route('/logout', methods=['GET'])
def logout():
    dev_mode = bool(strtobool(os.environ["DEV_MODE"]))
    if not dev_mode:
        session['logged_in'] = False
    return login()


if __name__ == '__main__':

    # Parse command line arguments
    args = parse_args()

    app.secret_key = os.urandom(24)
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    dev_mode = bool(strtobool(os.environ["DEV_MODE"]))
    app_name = os.environ["AppName"]
    conf = Util.get_crypto_dict(app_name)
    cfg_mgr = ConfigManager()
    config_client = cfg_mgr.get_config_client("etcd", conf)
    visualizerConfig = config_client.GetConfig("/" + app_name + "/config")
    jsonConfig = json.loads(visualizerConfig)

    globalenvConfig = config_client.GetConfig("/GlobalEnv/")
    globalConfig = json.loads(globalenvConfig)

    if globalConfig['PY_LOG_LEVEL'].lower() == 'debug':
        flaskDebug = True
    else:
        flaskDebug = False

    if dev_mode:
        app.run(host='0.0.0.0', port=jsonConfig['port'],
                debug=flaskDebug, threaded=True)
    else:
        # For Secure Session Cookie
        app.config.update(SESSION_COOKIE_SECURE=True)
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
        app.run(host='0.0.0.0', port=jsonConfig['port'],
                debug=flaskDebug, threaded=True, ssl_context=context)
