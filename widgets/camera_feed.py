from __future__ import annotations

import json
import socket
import struct
import sys
import threading
import time
import traceback
from collections import deque
from io import BytesIO

from PIL import Image, ImageFile
from PySide2.QtCore import QObject, Qt, Signal
from PySide2.QtGui import QImage, QPixmap
from PySide2.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSlider, QTabWidget, QVBoxLayout, QWidget,QSplitter)

IMAGE_BUFFER_SIZE = 1024
REMOTE_IP_ADDR = '10.9.5.107'  # '10.74.7.4'
FRAME_START_IDENTIFIER = b'\n_\x92\xc3\x9c>\xbe\xfe\xc1\x98'


DEBUG = True

ImageFile.LOAD_TRUNCATED_IMAGES = True


class Signals(QObject):
    imageReady = Signal(QImage)
    updateStatus = Signal(int, int, int)  # total,server process time, client time
    frameResize = Signal(int)


class SingletonMeta(type):
    def __call__(cls, *args, **kwargs):
        if not hasattr(cls, '_obj'):
            cls._obj = cls.__new__(cls)
            cls._obj.__init__(*args, **kwargs)
        return cls._obj


class RateTracker:
    def __init__(self, interval):
        self.deque = deque()
        self.interval = interval
        self.lock = threading.Lock()
    
    def __set__(self, instance, value):
        self.lock.acquire()
        ts = time.time()
        self.deque.appendleft((ts, value))
        self.lock.release()
    
    def __get__(self, instance, owner):
        try:
            if self.lock.acquire(False):
                try:
                    ts, value = self.deque.pop()
                    if time.time() - ts > self.interval:
                        while time.time() - ts > self.interval:
                            ts, value = self.deque.pop()
                    else:
                        self.deque.append((ts, value))
                except IndexError:
                    return 0
                
                if len(self.deque) == 1:
                    return self.deque[0][1]
                
                v = 0
                for ts, value in self.deque:
                    v += value
                try:
                    return v / (self.deque[0][0] - ts)
                except IndexError:
                    return 0
            else:
                return 0
        finally:
            self.lock.release()


class TrafficMonitor(metaclass=SingletonMeta):
    cam0 = RateTracker(2)
    cam1 = RateTracker(2)
    cam2 = RateTracker(2)
    cam3 = RateTracker(2)
    
    def __init__(self, n_camera: int):
        self._n_camera = n_camera
    
    @property
    def total(self):
        v = 0
        for i in range(self._n_camera):
            v += getattr(self, 'cam%d' % i)
        return v


class FrameRateMonitor(metaclass=SingletonMeta):  # not really a subclass, but the similar functionality
    cam0 = RateTracker(1)
    cam1 = RateTracker(1)
    cam2 = RateTracker(1)
    cam3 = RateTracker(1)
    
    def __init__(self, n_camera: int):
        self._n_camera = n_camera
    
    @property
    def total(self):
        v = 0
        for i in range(self._n_camera):
            v += getattr(self, 'cam%d' % i)
        return v / self._n_camera


class FrameDropMonitor(metaclass=SingletonMeta):
    cam0 = RateTracker(10)
    cam1 = RateTracker(10)
    cam2 = RateTracker(10)
    cam3 = RateTracker(10)
    
    def __init__(self, n_camera: int):
        self._n_camera = n_camera
    
    @property
    def total(self):
        v = 0
        for i in range(self._n_camera):
            v += getattr(self, 'cam%d' % i)
        return v / self._n_camera


class FeedReceiver(threading.Thread):
    def __init__(self, camera_feed: CameraFeed, camera_id: int):
        super().__init__()
        self.camera_id = camera_id
        self.camera_feed_widget = camera_feed
        self.signals = Signals()
        self.width = 960
    
    def run(self):
        self.signals.frameResize.connect(self.updateFrameSize)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(('0.0.0.0', 5801 + self.camera_id))
            # sock.sendto(FRAME_START_IDENTIFIER, (REMOTE_IP_ADDR, 5800))
            while True:
                try:
                    header = sock.recv(40)
                    while header[:10] != FRAME_START_IDENTIFIER:
                        #print('Waiting for frame start')
                        header = sock.recv(40)
                    n_packets, frame_id, time_started, server_time = struct.unpack('>IIdd', header[10:])
                    # print(n_packets, frame_id, time_started, server_time)
                    buf = bytes()
                    check = True
                    for i in range(n_packets):
                        packet = sock.recv(1024)
                        if int.from_bytes(packet[0:4], 'big') != i:
                            check = False
                        buf += packet[4:]
                    if check:
                        client_started = time.time()
                        setattr(TrafficMonitor(), 'cam%d' % self.camera_id, len(buf))
                        setattr(FrameRateMonitor(), 'cam%d' % self.camera_id, 1)
                        img = Image.open(BytesIO(buf))
                        aspect_ratio = img.size[0] / img.size[1]
                        img = img.resize((int(self.width), int(self.width // aspect_ratio)), Image.BICUBIC)
                        img = QImage(img.tobytes('raw', 'RGB'), *img.size, QImage.Format_RGB888)
                        self.signals.imageReady.emit(img)
                        self.signals.updateStatus.emit(
                                (time.time() - time_started) * 1000,  # multiply by 1000 to cast to milliseconds
                                server_time * 1000,
                                (time.time() - client_started) * 1000,
                        )
                except:
                    print(traceback.format_exc(), file=sys.stderr)
                    setattr(FrameDropMonitor(), 'cam%d' % self.camera_id, 1)
    
    def updateFrameSize(self, new_width):
        self.width = new_width


class CameraFeed(QWidget):
    def __init__(self, id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.id = id
        self.box = QHBoxLayout()
        self.setLayout(self.box)
        self.video_frame = QLabel()
        self.video_frame.setScaledContents(True)
        self.video_frame.setMinimumSize(1, 1)
        self.video_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(1, 1)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.box.addWidget(self.video_frame)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    
    def startReceiving(self):
        self.feed_receiver = FeedReceiver(self, self.id)
        self.setVideoFramePlaceHolder()
        self.feed_receiver.signals.imageReady.connect(self.updateImage)
        self.feed_receiver.start()
    
    def updateImage(self, data: QImage):
        img = QPixmap()
        img.convertFromImage(data)
        self.video_frame.setPixmap(img)
    
    def setVideoFramePlaceHolder(self):
        img = QImage(self.feed_receiver.width, self.feed_receiver.width // 16 * 9, QImage.Format_Grayscale8)
        img.fill(2)
        self.updateImage(img)
    


class Configuration(metaclass=SingletonMeta):
    def __init__(self, n_camera):
        self.n_camera = n_camera
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.lock = threading.Lock()
        self.configs = CONFIGURATIONS['cameras']
    
    def connect(self):
        self.lock.acquire()
        self.sock.connect((REMOTE_IP_ADDR, 5800))
        self.lock.release()
        
    def update_config(self, cam_num, resolution, quality):
        print(f'Updating for {cam_num}, res: {resolution}, qual: {quality}')
        try:
            self.configs['cam%d' % cam_num] = {'resolution': resolution, 'quality': quality}
            self.lock.acquire()
            self.sock.send(json.dumps(self.configs).encode())
        finally:
            self.lock.release()
    
    def change_settings(self, cam_num, cam_res, cam_qual):
        d = {'cam' + str(cam_num): {"cam_res": cam_res, "cam_qual": cam_qual}}
        self.sock.sendall(json.dumps(d).encode())
    
    def close(self):
        self.sock.close()
        configs_file = open("configs.json", 'w+')
        configs_file.write(json.dumps({'cameras': self.configs}))
        configs_file.close()


class Camera(QWidget):
    def __init__(self, id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.id = id
        self.image_quality=CONFIGURATIONS['cameras']['cam%d'%id]['quality']
        self.image_resolution = CONFIGURATIONS['cameras']['cam%d' % id]['resolution']
        
        self.box = QVBoxLayout()
        self.setLayout(self.box)
        
        self.tabs = QTabWidget()

        self.camera_feed = CameraFeed(self.id)
        
        self.status = QFrame()
        self.initStatus()
        
        self.box.addWidget(self.tabs)
        
        self.tabs.addTab(self.camera_feed, 'Camera')
        self.tabs.addTab(self.status, 'Status')
        
        
        self.setMinimumSize(1, 1)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    
    def initStatus(self):
        self.status_layout = QGridLayout()
        self.status.setLayout(self.status_layout)
        
        self.serverTime = QLabel()
        self.clientTime = QLabel()
        self.totalTime = QLabel()
        self.networkTime = QLabel()
        
        self.clientTime.setText('0.000 ms')
        self.serverTime.setText('0.000 ms')
        self.totalTime.setText('0.000 ms')
        self.networkTime.setText('0.000 ms')
        
        self.fps = QLabel()
        self.fps.setText('0.000 FPS')
        
        self.traffic = QLabel()
        self.traffic.setText('0.000 KB/s')
        
        self.frame_drop = QLabel()
        self.frame_drop.setText('0 FPS')
        
        # self.status_layout.addWidget(self.fps, 0, 0)
        
        self.status_layout.addWidget(QLabel("Traffic"), 0, 0)
        self.status_layout.addWidget(self.traffic, 0, 1)
        
        self.status_layout.addWidget(QLabel("Server"), 1, 0)
        self.status_layout.addWidget(self.serverTime, 1, 1)
        
        self.status_layout.addWidget(QLabel("Client"), 2, 0)
        self.status_layout.addWidget(self.clientTime, 2, 1)
        
        self.status_layout.addWidget(QLabel("Network"), 3, 0)
        self.status_layout.addWidget(self.networkTime, 3, 1)
        
        self.status_layout.addWidget(QLabel("Total"), 4, 0)
        self.status_layout.addWidget(self.totalTime, 4, 1)
        
        self.status_layout.addWidget(QLabel("Frame Rate"), 5, 0)
        self.status_layout.addWidget(self.fps, 5, 1)
        
        self.status_layout.addWidget(QLabel("Frame Drop"), 6, 0)
        self.status_layout.addWidget(self.frame_drop, 6, 1)
        
        self.quality_slider = QSlider(Qt.Horizontal)
        self.quality_slider.setMinimum(1)
        self.quality_slider.setMaximum(80)
        self.quality_slider.setSingleStep(1)
        self.quality_slider.setValue(self.image_quality)
        
        self.quality_label = QLabel(str(self.image_quality))
        self.quality_slider.valueChanged.connect(lambda n: self.quality_label.setText(str(n)))
        
        self.resolution_slider = QSlider(Qt.Horizontal, )
        self.resolution_slider.setMinimum(120)
        self.resolution_slider.setMaximum(1080)
        self.resolution_slider.setSingleStep(120)
        self.resolution_slider.setValue(self.image_resolution)
        
        self.resolution_label = QLabel(str(self.image_resolution))
        self.resolution_slider.valueChanged.connect(lambda n: self.resolution_label.setText(str(n)))
        
        self.status_layout.addWidget(QLabel("Image Quality"), 7, 0, columnspan=2)
        self.status_layout.addWidget(self.quality_slider, 8, 0)
        self.status_layout.addWidget(self.quality_label, 8, 1)
        
        self.status_layout.addWidget(QLabel("Image Resolution"), 9, 0, columnspan=2)
        self.status_layout.addWidget(self.resolution_slider, 10, 0)
        self.status_layout.addWidget(self.resolution_label, 10, 1)
        
        self.apply_button = QPushButton("Apply")
        self.status_layout.addWidget(self.apply_button, 11, 1)
        self.apply_button.clicked.connect(
            lambda e: Configuration().update_config(self.id, self.resolution_slider.value(), self.quality_slider.value()))
    
    def updateStatus(self, total, server, client):
        self.totalTime.setText('{: <4} ms'.format(str(total)))
        self.serverTime.setText('{: <4} ms'.format(str(server)))
        self.clientTime.setText('{: <4} ms'.format(str(client)))
        self.networkTime.setText('{: <4} ms'.format(str(total - server - client)))
        self.traffic.setText('{: <4} KB/s'.format(str(round(getattr(TrafficMonitor(), 'cam%d' % self.id) / 1024, 1))))
        self.fps.setText('{: <4} FPS'.format(str(round(getattr(FrameRateMonitor(), 'cam%d' % self.id), 1))))
        self.frame_drop.setText('{: <4} FPS'.format(str(round(getattr(FrameDropMonitor(), 'cam%d' % self.id), 1))))

    def startReceiving(self):
        
        self.camera_feed.startReceiving()
        self.camera_feed.feed_receiver.signals.updateStatus.connect(self.updateStatus)

class CameraPanel(QWidget):
    def __init__(self,n_camera,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.cameras=[]
        self.box=QVBoxLayout()
        self.setLayout(self.box)
        
        for i in range(n_camera):
            self.cameras.append(Camera(i))
        Configuration(n_camera)
        main_splitter=QSplitter(Qt.Vertical)
        main_splitter.addWidget(self.cameras[0])
        if n_camera==2:
            main_splitter.addWidget(self.cameras[1])
        elif n_camera==3:
            sub_splitter=QSplitter(Qt.Horizontal)
            sub_splitter.addWidget(self.cameras[1])
            sub_splitter.addWidget(self.cameras[2])
            main_splitter.addWidget(sub_splitter)
        elif n_camera==4:
            sub_splitter = QSplitter(Qt.Horizontal)
            sub_sub_splitter=QSplitter(Qt.Horizontal)
            sub_splitter.addWidget(sub_sub_splitter)
            sub_sub_splitter.addWidget(self.cameras[1])
            sub_sub_splitter.addWidget(self.cameras[2])
            sub_splitter.addWidget(self.cameras[3])
            main_splitter.addWidget(sub_splitter)
        
        self.box.addWidget(main_splitter)
        
    def connectRemote(self):
        """
        This function blocks until TCP connection succeeds.
        Call with caution
        """
        Configuration().connect()
        for cam in self.cameras:
            cam.startReceiving()
        
        

if __name__ == '__main__':
    from PySide2.QtWidgets import QApplication
    import os

    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    try:
        configs_file = open("configs.json", 'r')
        CONFIGURATIONS = json.loads(configs_file.read())
        configs_file.close()
    except FileNotFoundError:
        CONFIGURATIONS = {
            'cameras': {
                'cam0': {
                    'resolution': 240,
                    'quality'   : 25
                },
                'cam1': {
                    'resolution': 240,
                    'quality'   : 25
                },
                'cam2': {
                    'resolution': 240,
                    'quality'   : 25
                },
                'cam3': {
                    'resolution': 240,
                    'quality'   : 25
                }
            }
        }
    
    #signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QApplication([])
    
    app.setStyle('Fusion')
    TrafficMonitor(3)
    FrameRateMonitor(3)
    FrameDropMonitor(3)
    cp=CameraPanel(3)
    
    cp.connectRemote()
    cp.show()
    
    
    try:
        exit(app.exec_())
    finally:
        Configuration().close()
        
        
