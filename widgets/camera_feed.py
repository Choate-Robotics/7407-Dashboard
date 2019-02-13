#!/usr/local/bin/python3.7
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import socket
import struct
import sys
import threading
import time
import os
import traceback
import signal
import numpy as np
import multiprocessing as mp
import PySide2
import pyqtgraph as pg
from collections import deque
from io import BytesIO


from PIL import Image, ImageFile
from PySide2.QtCore import QObject, Qt, Signal, QTimer, QThread
from PySide2.QtGui import QImage, QPixmap
from PySide2.QtWidgets import (
    QFrame,
    QGridLayout,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QSplitter,
    QScrollArea,
    QComboBox,
    QMessageBox
)

IMAGE_BUFFER_SIZE = 1024
REMOTE_IP_ADDR = '10.74.7.14' #'10.5.5.100'  # '10.9.5.5'  # '10.74.7.12'
FRAME_START_IDENTIFIER = b'\n_\x92\xc3\x9c>\xbe\xfe\xc1\x98'
DEBUG = True

ImageFile.LOAD_TRUNCATED_IMAGES = True

pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')


class Signals(QObject):
    imageReady = Signal(QImage)
    updateStatus = Signal(float, float, float)  # total,server process time, client time
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
        return v / self._n_camera


class FeedReceiver(threading.Thread):
    def __init__(self, camera_feed: CameraFeed, camera_id: int, app:QApplication):
        super().__init__()
        self.camera_id = camera_id
        self.camera_feed_widget = camera_feed
        self.signals = Signals()
        self.width = 960
        self._terminate = False
        self.initial_connection_succeeded=False
        app.aboutToQuit.connect(self.terminate)
    
    def run(self):
        self.signals.frameResize.connect(self.updateFrameSize)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(('0.0.0.0', 5801 + self.camera_id))
            sock.settimeout(1)
            print('UDP socket bound to port %d' % (5801 + self.camera_id))
            # sock.sendto(FRAME_START_IDENTIFIER, (REMOTE_IP_ADDR, 5800))
            last_frame_id = 0
            while not self._terminate:
                try:
                    header = sock.recv(40)
                    while header[:10] != FRAME_START_IDENTIFIER:
                        # print('Waiting for frame start')
                        header = sock.recv(40)
                    n_packets, frame_id, time_started, server_time = struct.unpack('>IIdd', header[10:])
                    
                    if frame_id == last_frame_id + 1:
                        last_frame_id += 1
                    else:
                        setattr(FrameDropMonitor(), 'cam%d' % self.camera_id, 1)
                        last_frame_id = frame_id
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
                        #cv2.imdecode(np.fromstring(buf,dtype=np.uint8))
                        img = Image.open(BytesIO(buf))
                        if img.size[0]%60!=0:
                            aspect_ratio = img.size[0] / img.size[1]
                            img = img.resize((int(self.width), int(self.width // aspect_ratio)), Image.BICUBIC)
                        img = QImage(img.tobytes('raw', 'RGB'), *img.size, QImage.Format_RGB888)
                        self.signals.imageReady.emit(img)
                        self.signals.updateStatus.emit(
                                round((time.time() - time_started) * 1000,2),  # multiply by 1000 to cast to milliseconds
                                round(server_time * 1000,2),
                                round((time.time() - client_started) * 1000,2)
                        )
                    else:
                        setattr(FrameDropMonitor(), 'cam%d' % self.camera_id, 1)
                except socket.timeout:
                    if self.initial_connection_succeeded:
                        if Configuration().lock.acquire(False):
                            Configuration().lock.release() # Another thread issued reconnection already
                        else:
                            Configuration().reconnect()
                except:
                    print(traceback.format_exc(), file=sys.stderr)
                    setattr(FrameDropMonitor(), 'cam%d' % self.camera_id, 1)
                else:
                    if not self.initial_connection_succeeded:
                        self.initial_connection_succeeded=True
                        print("UDP connection to %s:%d established"%(REMOTE_IP_ADDR,self.camera_id+5801))
            else:
                print("Receiver thread for camera %d terminated" % self.camera_id)
    
    def updateFrameSize(self, new_width):
        self.width = new_width
    
    def terminate(self):
        self._terminate = True


class Indicator(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class CameraFeed(QWidget):
    def __init__(self, id,app:QApplication, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.id = id
        self.app=app
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
        self.feed_receiver = FeedReceiver(self, self.id,self.app)
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
    def __init__(self, n_camera, camera_panel:CameraPanel):
        self.n_camera = n_camera
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.lock = threading.Lock()
        self.configs = CONFIGURATIONS['cameras']
        self.sock.bind(('0.0.0.0', 5800))
        self.sock.settimeout(1)
        print("TCP socket bound to port 5800")
        self.is_connected = False
        self.camera_panel=camera_panel
    
    def connect(self):
        self.lock.acquire()
        print("Connecting to %s:5800..." % REMOTE_IP_ADDR, end='')
        try:
            self.sock.connect((REMOTE_IP_ADDR, 5800))
            self.sock.recv(4)
            t1 = time.time()
            self.sock.send(struct.pack('ff', t1, time.time()))
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            if e.errno==56: # all three exception types have errno attribute
                # connection already established
                print('connected')
                return True
            print("failed: %s" % e)
            self.sock.close() # Reset the socket
            self.sock=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(1)
            self.sock.bind(('0.0.0.0', 5800))
            self.lock.release()
            return False
        else:
            print("connected")
        if os.name == 'nt':  # Reset TCP connections instead of waiting for ACK from peer
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('hh', 1, 0))
        else:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
        self.sock.send(json.dumps(self.configs).encode()+b'|')
        self.is_connected = True
        self.lock.release()
        return True
    
    def reconnect(self):
        if self.lock.acquire(False):
            try:
                self.sock.recv(1)
            except (ConnectionResetError,socket.timeout):
                self.sock.close()
                
                self.camera_panel.reconnecting.show()
                self.camera_panel.total_traffic.hide()
                self.sock=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(1)
                self.sock.bind(('0.0.0.0', 5800))
                self.lock.release()
                while not self.connect():
                    self.camera_panel.reconnecting.setText(self.camera_panel.reconnecting.text()+'.')
                    time.sleep(0.1)
                self.camera_panel.reconnecting.setText("Disconnected. Trying to reconnect")
                self.camera_panel.reconnecting.hide()
                self.camera_panel.total_traffic.show()
            except:
                print(traceback.format_exc(),file=sys.stderr)
                self.lock.release()
    
    
    def update_config(self, cam_num, resolution, quality):
        try:
            self.configs['cam%d' % cam_num] = {'resolution': resolution, 'quality': quality}
            self.lock.acquire()
            self.sock.send(json.dumps(self.configs).encode()+b'|')
        finally:
            self.lock.release()
    
    def change_settings(self, cam_num, cam_res, cam_qual):
        d = {'cam' + str(cam_num): {"cam_res": cam_res, "cam_qual": cam_qual}}
        self.sock.sendall(json.dumps(d).encode())
    
    def close(self):
        if self.is_connected:
            self.lock.acquire()
            self.sock.close()
            configs_file = open("configs.json", 'w+')
            configs_file.write(json.dumps({'cameras': self.configs}))
            configs_file.close()
            print("TCP Connection closed", flush=True)
            # Flush the stdout buffer because it's likely to be the last thing printed
            self.is_connected = False
            self.lock.release()


class StatusPlotItem(pg.PlotItem):
    def __init__(self, *args, arr_size=9000, **kwargs):
        super().__init__(*args, **kwargs)
        self.arr_size = arr_size
        self.setClipToView(True)
        self.setDownsampling(mode='subsample')
        self.setLabel('bottom', 'Time')
        self.curve = self.plot()
        self.__x = np.full((self.arr_size,), np.inf, dtype=np.float)
        self.__y = np.zeros((self.arr_size,), dtype=np.short)
        self.index = 0
        self.time_started = None
        self.getViewBox().setAutoVisible(True,True)
        for axis in self.axes.values():
            axis['item'].enableAutoSIPrefix(False)
    
    @property
    def value(self):
        return self.__y[-1]
    
    @value.setter
    def value(self, v):
        if self.time_started is None:
            self.time_started = time.time()
        current_time = time.time() - self.time_started
        self.__y[self.index] = v
        self.__x[self.index] = current_time
        self.index += 1
        self.setLimits(xMin=current_time - 18, xMax=current_time+2)
        if self.index == self.arr_size:  # expends the array
            print('%s: Array Resizing'%round(current_time,2))
            self.arr_size += 3600  # 30 FPS for 120 seconds
            new_x = np.full((self.arr_size,), np.inf, dtype=np.float)
            new_x[:self.__x.shape[0]] = self.__x
            new_y = np.zeros((self.arr_size,), dtype=np.ushort)
            new_y[:self.__y.shape[0]] = self.__y
            self.__x = new_x
            self.__y = new_y
            # self.index=0
    
    def update(self):
        if self.index>20:
            self.curve.setData(self.__x[10:], self.__y[10:]) # The first few data points are very not accurate
        else:
            self.curve.setData(self.__x, self.__y)

class Camera(QWidget):
    modes = (
        ('Manual', 0, 0),
        ('Optimize for traffic (aggressive)',60,10),
        ('Optimize for traffic (moderate)',120,25),
        ('Optimize for latency (aggressive)',60,80),
        ('Optimize for latency (moderate)',120,80),
        ('Optimize for video quality',480,30)
    )
    
    def __init__(self, id, app:QApplication, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.id = id
        self.image_quality = CONFIGURATIONS['cameras']['cam%d' % id]['quality']
        self.image_resolution = CONFIGURATIONS['cameras']['cam%d' % id]['resolution']
        
        self.box = QVBoxLayout()
        self.setLayout(self.box)
        
        self.tabs = QTabWidget()
        
        self.camera_feed = CameraFeed(self.id,app)
        
        self.status_frame = QFrame()
        self.status_frame.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.status_frame.setMinimumSize(250, 340)
        self.status = QScrollArea()
        self.status.setWidget(self.status_frame)
        self.initStatus()
        
        self.network_graphs = pg.GraphicsLayoutWidget()
        self.traffic_graphs = pg.GraphicsLayoutWidget()
        self.frame_rate_graphs = pg.GraphicsLayoutWidget()
        self.initGraphs()
        
        self.box.addWidget(self.tabs)
        
        self.tabs.addTab(self.camera_feed, 'Camera')
        self.tabs.addTab(self.status, 'Status')
        self.tabs.addTab(self.traffic_graphs, "Traffic")
        self.tabs.addTab(self.network_graphs, "Latency")
        self.tabs.addTab(self.frame_rate_graphs, "Video")
        
        self.setMinimumSize(1, 1)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.updateAllGraphs)
        self.timer.start(100)
    
    def initStatus(self):
        self.status_layout = QGridLayout()
        self.status_frame.setLayout(self.status_layout)
        
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
        
        self.status_layout.addWidget(QLabel("Frame Rate"), 0, 0)
        self.status_layout.addWidget(self.fps, 0, 1)
        
        self.status_layout.addWidget(QLabel("Frame Drop"), 1, 0)
        self.status_layout.addWidget(self.frame_drop, 1, 1)
        
        self.status_layout.addWidget(QLabel("Server"), 2, 0)
        self.status_layout.addWidget(self.serverTime, 2, 1)
        
        self.status_layout.addWidget(QLabel("Client"), 3, 0)
        self.status_layout.addWidget(self.clientTime, 3, 1)
        
        self.status_layout.addWidget(QLabel("Network"), 4, 0)
        self.status_layout.addWidget(self.networkTime, 4, 1)
        
        self.status_layout.addWidget(QLabel("Total"), 5, 0)
        self.status_layout.addWidget(self.totalTime, 5, 1)
        
        self.status_layout.addWidget(QLabel("Traffic"), 6, 0)
        self.status_layout.addWidget(self.traffic, 6, 1)
        
        self.mode_selection = QComboBox()
        self.mode_selection.wheelEvent=self.status.wheelEvent # Monkey patch it so the selection doesn't change
        self.mode_selection.setEnabled(False)
        self.mode_selection.setSizePolicy(QSizePolicy.Minimum,QSizePolicy.Fixed)
        for i,mode in enumerate(self.modes):
            self.mode_selection.addItem(mode[0])
            if self.image_resolution==mode[1] and self.image_quality==mode[2]:
                self.mode_selection.setCurrentIndex(i)
        
        self.status_layout.addWidget(self.mode_selection, 7, 0, columnspan=2)
        self.mode_selection.currentIndexChanged.connect(self.updateMode)
        
        self.quality_slider = QSlider(Qt.Horizontal)
        self.quality_slider.setMinimum(1)
        self.quality_slider.setMaximum(80)
        self.quality_slider.setSingleStep(1)
        self.quality_slider.setValue(self.image_quality)
        self.quality_slider.wheelEvent=self.status.wheelEvent
        self.quality_slider.setEnabled(False)
        
        self.quality_label = QLabel(str(self.image_quality))
        self.quality_slider.valueChanged.connect(lambda n: self.quality_label.setText(str(n)))
        
        self.resolution_slider = QSlider(Qt.Horizontal, )
        self.resolution_slider.setMinimum(60)
        self.resolution_slider.setMaximum(1080)
        self.resolution_slider.setSingleStep(120)
        self.resolution_slider.setValue(self.image_resolution)
        self.resolution_slider.wheelEvent=self.status.wheelEvent
        self.resolution_slider.setEnabled(False)
        
        self.resolution_label = QLabel(str(self.image_resolution))
        self.resolution_slider.valueChanged.connect(lambda n: self.resolution_label.setText(str(n)))
        
        self.status_layout.addWidget(QLabel("Image Quality"), 8, 0, columnspan=2)
        self.status_layout.addWidget(self.quality_slider, 9, 0)
        self.status_layout.addWidget(self.quality_label, 9, 1)
        
        self.status_layout.addWidget(QLabel("Image Resolution"), 10, 0, columnspan=2)
        self.status_layout.addWidget(self.resolution_slider, 11, 0)
        self.status_layout.addWidget(self.resolution_label, 11, 1)
        
        self.apply_button = QPushButton("Apply")
        self.apply_button.setEnabled(False)
        self.status_layout.addWidget(self.apply_button, 12, 0)
        
        self.apply_button.clicked.connect(self.updateConfiguration)
    
    def updateMode(self, index):
        mode_name,resolution,quality=self.modes[index]
        if mode_name=='Manual':
            self.apply_button.setEnabled(True)
            self.resolution_slider.setEnabled(True)
            self.quality_slider.setEnabled(True)
        else:
            self.apply_button.setEnabled(False)
            self.resolution_slider.setEnabled(False)
            self.quality_slider.setEnabled(False)
            self.resolution_slider.setValue(resolution)
            self.quality_slider.setValue(quality)
            self.updateConfiguration()
            
        
    
    def updateConfiguration(self):
        try:
            Configuration().update_config(self.id, self.resolution_slider.value(), self.quality_slider.value())
        except (ConnectionResetError,BrokenPipeError):
            Configuration().reconnect()
        
    def initGraphs(self):
        self.traffic_plot = StatusPlotItem()
        self.traffic_plot.setTitle("Traffic")
        self.traffic_plot.setLabel("left", 'Data Transmitted', 'KB/s')
        self.traffic_graphs.addItem(self.traffic_plot, row=0, col=0)
        
        self.network_plot = StatusPlotItem()
        self.network_plot.setTitle("Network Time")
        self.network_plot.setLabel("left", "Latency (ms)", )
        self.network_graphs.addItem(self.network_plot, row=0, col=2)
        
        self.client_time_plot = StatusPlotItem()
        self.client_time_plot.setTitle("Client Time")
        self.client_time_plot.setLabel("left", "Latency (ms)", )
        self.network_graphs.addItem(self.client_time_plot, row=0, col=1)
        
        self.total_time_plot = StatusPlotItem()
        self.total_time_plot.setTitle("Total Latency")
        self.total_time_plot.setLabel("left", "Latency (ms)", )
        self.network_graphs.addItem(self.total_time_plot, row=0, col=0)
        
        self.frame_rate_plot = StatusPlotItem()
        self.frame_rate_plot.setLabel('left', 'Frame Per Second')
        self.frame_rate_plot.setTitle("Frame Rate")
        self.frame_rate_graphs.addItem(self.frame_rate_plot, row=0, col=0)
        
        self.frame_drop_plot = StatusPlotItem()
        self.frame_rate_plot.setLabel('left', 'Frame Per Second')
        self.frame_drop_plot.setTitle('Frame Drop')
        self.frame_rate_graphs.addItem(self.frame_drop_plot, row=0, col=1)
    
    def updateStatus(self, total, server, client):
        self.totalTime.setText('{: <4} ms'.format(str(total)))
        self.total_time_plot.value = total
        
        self.serverTime.setText('{: <4} ms'.format(str(server)))
        
        self.clientTime.setText('{: <4} ms'.format(str(client)))
        self.client_time_plot.value = client
        
        self.networkTime.setText('{: <4} ms'.format(str( round(total - server - client,2) )))
        self.network_plot.value = total - server - client
        
        self.traffic.setText('{: <4} KB/s'.format(str(round(getattr(TrafficMonitor(), 'cam%d' % self.id) / 1024, 1))))
        self.traffic_plot.value = getattr(TrafficMonitor(), 'cam%d' % self.id) / 1024
        
        self.fps.setText('{: <4} FPS'.format(str(round(getattr(FrameRateMonitor(), 'cam%d' % self.id), 1))))
        self.frame_rate_plot.value = getattr(FrameRateMonitor(), 'cam%d' % self.id)
        
        self.frame_drop_plot.value = getattr(FrameDropMonitor(), 'cam%d' % self.id)
        self.frame_drop.setText('{: <4} FPS'.format(str(round(getattr(FrameDropMonitor(), 'cam%d' % self.id), 1))))
        
        # self.updateAllGraphs()
    
    def updateAllGraphs(self):
        self.total_time_plot.update()
        self.client_time_plot.update()
        self.frame_rate_plot.update()
        self.frame_drop_plot.update()
        self.network_plot.update()
        self.traffic_plot.update()
    
    def startReceiving(self):
        self.camera_feed.startReceiving()
        self.time_started = time.time()
        self.camera_feed.feed_receiver.signals.updateStatus.connect(self.updateStatus)


class CameraPanel(QWidget):
    # __obj=None
    # def __new__(cls, *args, **kwargs):
    #     if cls.__obj is None:
    #         pass
    #         cls.__obj=QWidget.__new__(cls,*args,**kwargs)
    #         QWidget.__init__(cls.__obj)
    #         cls.__obj.__init__(*args,**kwargs)
    #     return cls.__obj
    #
    def __init__(self, n_camera, app:QApplication, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cameras = []
        self.box = QVBoxLayout()
        self.setLayout(self.box)
        
        self.connectButton = QPushButton("Connect")
        self.connectButton.clicked.connect(self.connectRemote)
        self.reconnecting=QLabel("Disconnected. Trying to reconnect")
        self.reconnecting.setWordWrap(True)
        self.total_traffic=QLabel("0.000 KB/s")
        self.restart_remote=QPushButton("Restart Remote")
        self.restart_remote.setSizePolicy(QSizePolicy.Maximum,QSizePolicy.Expanding)
        self.restart_remote.clicked.connect(self.restartRemote)
        
        self.top_frame=QFrame()
        self.top_frame.setSizePolicy(QSizePolicy.Minimum,QSizePolicy.Maximum)
        self.top_grid=QGridLayout()
        self.top_grid.setContentsMargins(0,0,0,0)
        self.top_frame.setLayout(self.top_grid)
        
        self.top_grid.addWidget(self.connectButton,0,0)
        self.top_grid.addWidget(self.reconnecting,0,0)
        self.top_grid.addWidget(self.total_traffic,0,0)
        self.top_grid.addWidget(self.restart_remote,0,1)
        
        self.total_traffic.hide()
        self.reconnecting.hide()
        
        self.box.addWidget(self.top_frame)

        
        self.timer=QTimer()
        self.timer.timeout.connect(self.updateTraffic)
        self.timer.start(100)
        
        for i in range(n_camera):
            self.cameras.append(Camera(i,app))
        
        Configuration(n_camera,self)
        TrafficMonitor(n_camera)
        FrameRateMonitor(n_camera)
        FrameDropMonitor(n_camera)
        
        main_splitter = QSplitter(Qt.Vertical)
        main_splitter.addWidget(self.cameras[0])
        if n_camera == 2:
            main_splitter.addWidget(self.cameras[1])
        elif n_camera == 3:
            sub_splitter = QSplitter(Qt.Horizontal)
            sub_splitter.addWidget(self.cameras[1])
            sub_splitter.addWidget(self.cameras[2])
            main_splitter.addWidget(sub_splitter)
        elif n_camera == 4:
            sub_splitter = QSplitter(Qt.Horizontal)
            sub_sub_splitter = QSplitter(Qt.Horizontal)
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
        if Configuration().connect():
            self.connectButton.hide()
            self.total_traffic.show()
            for cam in self.cameras:
                cam.startReceiving()
                cam.mode_selection.setEnabled(True)
                cam.updateMode(cam.mode_selection.currentIndex())
    
    def restartRemote(self):
        os.system(f'ssh root@{REMOTE_IP_ADDR} systemctl restart vision-server.service')
        if self.connectButton.isVisible():
            self.connectRemote()
        else:
            Configuration().reconnect()
    
    def updateTraffic(self):
        self.total_traffic.setText('{:<4} KB/s'.format(round(TrafficMonitor().total/1024,2)))




def close_TCP(signum, frame):
    print("Signal %d received. Disconnecting..." % signum, flush=True)
    Configuration().close()


signal.signal(signal.SIGINT, close_TCP)
signal.signal(signal.SIGTERM, close_TCP)
if os.name != 'nt':
    signal.signal(signal.SIGQUIT, close_TCP)

os.chdir(os.path.dirname(os.path.abspath(__file__)))

try:
    configs_file = open("configs.json", 'r')
    CONFIGURATIONS = json.loads(configs_file.read())
    configs_file.close()
except (FileNotFoundError, ValueError):
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

__all__=['CameraPanel']

if __name__ == '__main__':
    from PySide2.QtWidgets import QApplication
    
    app = QApplication([])
    
    app.setStyle('Fusion')
    
    # cp.connectRemote()
    camera_panel = CameraPanel(2)
    camera_panel.setWindowFlag(Qt.WindowStaysOnTopHint)
    camera_panel.show()
    
    try:
        app.exec_()
    finally:
        Configuration().close()
        sys.exit(0)
