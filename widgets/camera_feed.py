from __future__ import annotations

import socket
import threading
from collections import deque
from io import BytesIO
import time

from PIL import Image

from PySide2.QtCore import QObject, Signal,Qt
from PySide2.QtGui import QImage, QPixmap
from PySide2.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QSpacerItem, QVBoxLayout, QWidget, QTabWidget, QFrame, QGridLayout,QSlider
import struct

IMAGE_BUFFER_SIZE = 1024
REMOTE_IP_ADDR = '10.9.5.107'  # '10.74.7.4'
FRAME_START_IDENTIFIER = b'\n_\x92\xc3\x9c>\xbe\xfe\xc1\x98'

DEFAULT_IMAGE_QUALITY=25
DEFAULT_RESOLUTION=240

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
    cam0 = RateTracker(5)
    cam1 = RateTracker(5)
    cam2 = RateTracker(5)
    cam3 = RateTracker(5)
    
    def __init__(self, n_camera: int):
        self._n_camera = n_camera
    
    @property
    def total(self):
        v = 0
        for i in range(self._n_camera):
            v += getattr(self, 'cam%d' % i)
        return v / self._n_camera


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


class FeedReceiver(threading.Thread):
    def __init__(self, camera_feed: CameraFeed, camera_id: int):
        super().__init__()
        self.camera_id = camera_id
        self.camera_feed_widget = camera_feed
        self.signals = Signals()
        self.width = 960
        self.signals.frameResize.connect(self.updateFrameSize)
        

    
    def run(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(('0.0.0.0', 5801 + self.camera_id))
            sock.sendto(FRAME_START_IDENTIFIER, (REMOTE_IP_ADDR, 5800))
            while True:
                try:
                    header = sock.recv(32)
                    while header[:10] != FRAME_START_IDENTIFIER:
                        print('Waiting for frame start')
                        header = sock.recv(32)
                    n_packets, frame_id, time_started, server_time = struct.unpack('>BIdd', header[10:])
                    buf = bytes()
                    check = True
                    for i in range(n_packets):
                        packet = sock.recv(1024)
                        if packet[0] != i:
                            check = False
                        buf += packet[1:]
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
                                (time.time() - time_started) * 1000,
                                server_time * 1000,
                                (time.time() - client_started) * 1000,
                        )
                except:
                    raise
        
    def updateFrameSize(self,new_width):
        self.width=new_width

class CameraFeed(QWidget):
    def __init__(self, id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.id = id
        self.box = QHBoxLayout()
        self.setLayout(self.box)
        self.video_frame = QLabel()
        #self.video_frame.setScaledContents(True)
        self.video_frame.setMinimumSize(1, 1)
        self.video_frame.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        self.box.addWidget(self.video_frame)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    
    def startReceiving(self):
        self.feed_receiver = FeedReceiver(self, self.id)
        self.feed_receiver.signals.imageReady.connect(self.updateImage)
        self.feed_receiver.start()
    
    def updateImage(self, data: QImage):
        img = QPixmap()
        img.convertFromImage(data)
        self.video_frame.setPixmap(img)
    
    def setVideoFramePlaceHolder(self):
        img=QImage(self.feed_receiver.width, self.feed_receiver.width // 16 * 9, QImage.Format_Grayscale8)
        img.fill(2)
        self.updateImage(img)
        
    def resizeEvent(self, event):
        self.feed_receiver.signals.frameResize.emit(self.frameGeometry().width())
        self.setVideoFramePlaceHolder()
        event.accept()

class CameraFeedEnclosing(QWidget):
    def __init__(self, id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.id = id
        
        self.box = QVBoxLayout()
        self.setLayout(self.box)
        
        self.tabs = QTabWidget()
        
        self.camera_feed = CameraFeed(self.id)
        self.camera_feed.startReceiving()
        
        self.status = QFrame()
        self.initStatus()
        
        self.box.addWidget(self.tabs)
        
        self.tabs.addTab(self.camera_feed, 'Camera')
        self.tabs.addTab(self.status, 'Status')

        self.camera_feed.feed_receiver.signals.updateStatus.connect(self.updateStatus)
    
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

        self.quality_slider = QSlider(Qt.Horizontal, )
        self.quality_slider.setMinimum(1)
        self.quality_slider.setMaximum(100)
        self.quality_slider.setSingleStep(1)
        self.quality_slider.setValue(DEFAULT_IMAGE_QUALITY)
    
        self.resolution_slider = QSlider(Qt.Horizontal, )
        self.resolution_slider.setMinimum(120)
        self.resolution_slider.setMaximum(1080)
        self.resolution_slider.setSingleStep(120)
        self.resolution_slider.setValue(DEFAULT_RESOLUTION)
        
        self.status_layout.addWidget(QLabel("Image Quality"),6,0,columnspan=2)
        self.status_layout.addWidget(self.quality_slider,7,0)
        
        self.status_layout.addWidget(QLabel("Image Resolution"),8,0,columnspan=2)
        self.status_layout.addWidget(self.resolution_slider,9,0)
    
    def updateStatus(self, total, server, client):
        self.totalTime.setText('{: <4} ms'.format(str(total)))
        self.serverTime.setText('{: <4} ms'.format(str(server)))
        self.clientTime.setText('{: <4} ms'.format(str(client)))
        self.networkTime.setText('{: <4} ms'.format(str(total - server - client)))
        self.traffic.setText('{: <4} KB/s'.format(str(round(getattr(TrafficMonitor(), 'cam%d' % self.id) / 1024, 1))))
        self.fps.setText('{: <4} FPS'.format(str(round(getattr(FrameRateMonitor(), 'cam%d' % self.id), 1))))


if __name__ == '__main__':
    from PySide2.QtWidgets import QApplication
    import signal
    
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QApplication([])
    
    app.setStyle('Fusion')
    TrafficMonitor(4)
    FrameRateMonitor(4)
    
    en = CameraFeedEnclosing(0)
    
    en.show()
    
    app.exec_()
