from __future__ import annotations

from PySide2.QtWidgets import QWidget, QGridLayout, QLabel
from PySide2.QtGui import QImage, QPixmap, QPainter
from PySide2.QtCore import QObject, Signal, Slot

from PySide2.QtMultimedia import QMultimedia, QMediaPlayer
from PySide2.QtMultimediaWidgets import QVideoWidget
from io import BytesIO
import threading
import time
import socket

IMAGE_BUFFER_SIZE = 1024 * 1024  # 1MB
REMOTE_IP_ADDR = '10.9.5.107'


class Signals(QObject):
    imageReady = Signal(bytes)


class FeedReceiver(threading.Thread):
    def __init__(self, camera_feed: CameraFeed):
        super().__init__()
        self.camera_feed_widget = camera_feed
        self.signals = Signals()
    
    def run(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(b'Hello\n', (REMOTE_IP_ADDR, 5801))
            while True:
                self.signals.imageReady.emit(sock.recv(IMAGE_BUFFER_SIZE))


class CameraFeed(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.grid = QGridLayout()
        self.setLayout(self.grid)
        self.video_frame = QLabel()
        self.grid.addWidget(self.video_frame)
    
    def startReceiving(self):
        self.feed_receiver = FeedReceiver(self)
        self.feed_receiver.signals.imageReady.connect(self.updateImage)
        self.feed_receiver.start()
    
    @Slot(bytes)
    def updateImage(self, data: bytes):
        img = QPixmap()
        img.loadFromData(data)
        self.video_frame.setPixmap(img)


if __name__ == '__main__':
    from PySide2.QtWidgets import QApplication
    
    app = QApplication([])
    
    feed = CameraFeed()
    feed.startReceiving()
    
    feed.show()
    app.exec_()
