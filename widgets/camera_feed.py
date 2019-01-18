from __future__ import annotations

from PySide2.QtWidgets import QWidget, QHBoxLayout,QVBoxLayout, QLabel, QSizePolicy,QSpacerItem
from PySide2.QtGui import QImage, QPixmap, QPainter
from PySide2.QtCore import QObject, Signal, Slot

from PySide2.QtMultimedia import QMultimedia, QMediaPlayer
from PySide2.QtMultimediaWidgets import QVideoWidget
from io import BytesIO
from PIL import Image, ImageQt
import threading
import time
import socket

IMAGE_BUFFER_SIZE = 1024
REMOTE_IP_ADDR = '10.9.5.107'  # '10.74.7.4'
HANDSHAKE_SIGNATURE = b'\n_\x92\xc3\x9c>\xbe\xfe\xc1\x98'


class Signals(QObject):
    imageReady = Signal(QImage)


class FeedReceiver(threading.Thread):
    def __init__(self, camera_feed: CameraFeed, port: int):
        super().__init__()
        self.port = port
        self.camera_feed_widget = camera_feed
        self.signals = Signals()
    
    def run(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(('0.0.0.0',self.port))
            sock.sendto(HANDSHAKE_SIGNATURE, (REMOTE_IP_ADDR, 5800))
            while True:
                handshake = sock.recv(11)
                while handshake[:10] != HANDSHAKE_SIGNATURE:
                    handshake = sock.recv(11)
                n_packets = handshake[10]
                buf = bytes()
                check = True
                for i in range(n_packets):
                    packet = sock.recv(1024)
                    if packet[0] != i:
                        check = False
                    buf += packet[1:]
                if check:
                    img = Image.open(BytesIO(buf))
                    img = img.resize((480, 307))
                    img = QImage(img.tobytes('raw', 'RGB'), *img.size, QImage.Format_RGB888)
                    self.signals.imageReady.emit(img)


class CameraFeed(QWidget):
    def __init__(self, port, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.port = port
        self.box = QVBoxLayout()
        self.setLayout(self.box)
        
        self.processingTime=QLabel()
        
        sp=self.processingTime.sizePolicy()
        sp.setVerticalPolicy(QSizePolicy.Maximum)
        self.processingTime.setSizePolicy(sp)
        
        self.processingTime.setText('0 ms')
        
        self.fps=QLabel()
        sp=self.fps.sizePolicy()
        sp.setVerticalPolicy(QSizePolicy.Maximum)
        self.fps.setSizePolicy(sp)
        self.fps.setText('0 FPS')
        
        self.statusBox=QHBoxLayout()
        
        self.statusBox.addWidget(self.processingTime)
        self.statusBox.addItem(QSpacerItem(20, 0, QSizePolicy.Expanding, QSizePolicy.Expanding))
        self.statusBox.addWidget(self.fps)
        #self.statusBox.addStretch(0)
        
        self.box.addLayout(self.statusBox)
        
        self.video_frame = QLabel()
        sp=self.video_frame.sizePolicy()
        sp.setVerticalPolicy(QSizePolicy.Expanding)
        sp.setHorizontalPolicy(QSizePolicy.Expanding)
        self.video_frame.setSizePolicy(sp)
        self.box.addWidget(self.video_frame)

    
    def startReceiving(self):
        self.feed_receiver = FeedReceiver(self, self.port)
        self.feed_receiver.signals.imageReady.connect(self.updateImage)
        self.feed_receiver.start()
    
    def updateImage(self, data: bytes):
        img = QPixmap()
        img.convertFromImage(data)
        self.video_frame.setPixmap(img)


if __name__ == '__main__':
    from PySide2.QtWidgets import QApplication
    
    app = QApplication([])
    
    feed1 = CameraFeed(5801)
    feed1.startReceiving()
    
    feed1.show()
    app.exec_()
