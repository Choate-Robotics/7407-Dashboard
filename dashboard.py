from PySide2.QtCore import Qt
from PySide2.QtWidgets import (QDesktopWidget, QFrame, QGridLayout, QLabel, QSizePolicy, QSlider, QSplitter, QVBoxLayout, QWidget)

from widgets import Minimap, StreamError, StreamInput, StreamOutput


class Simulator(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowStaysOnTopHint)

        self.stdout = StreamOutput()
        self.stderr = StreamError()
        self.exec = StreamInput()

        self.frame = QFrame()
        self.screen = QDesktopWidget().screenGeometry()
        self.setGeometry(self.screen)
        self.grid = QGridLayout()
        self.frame.setLayout(self.grid)
        self.setLayout(self.grid)
        self.map = Minimap()

        # -- setting splitters
        splitter_bottom = QSplitter(Qt.Horizontal)  # STDIN, STDOUT
        splitter_main = QSplitter(Qt.Vertical)  # Map ((STDIN,STDOUT), STDERR)
        # --------------

        # -- top --
        ''' frame = QFrame()
        grid = QGridLayout()
        frame.setLayout(grid)
        splitter_main.addWidget(frame)
        grid.addWidget(self.map, 0, 0, 10, 1)

        slider_zoom = QSlider(Qt.Horizontal)
        slider_zoom.setMinimum(100)
        slider_zoom.setMaximum(1000)
        grid.addWidget(slider_zoom, 1, 1)

        sp = QSizePolicy()
        sp.setVerticalPolicy(QSizePolicy.Maximum)

        label = QLabel("Zoom")
        label.setSizePolicy(sp)
        grid.addWidget(label, 0, 1)

        zoom_label = QLabel("1")
        zoom_label.setSizePolicy(sp)

        slider_zoom.valueChanged.connect(lambda n: zoom_label.setText(str(n / 100)))

        grid.addWidget(zoom_label, 2, 1, Qt.AlignHCenter)

        splitter_main.addWidget(frame)'''
        # ------

        # -- bottom left --
        box = QVBoxLayout()
        frame = QFrame()
        frame.setLayout(box)
        box.addWidget(QLabel('Exec'))
        box.addWidget(self.exec)
        splitter_bottom.addWidget(frame)
        # -------

        # -- bottom middle --
        box = QVBoxLayout()
        frame = QFrame()
        frame.setLayout(box)
        splitter_bottom.addWidget(frame)
        box.addWidget(QLabel('Output'))
        box.addWidget(self.stdout)
        # -------

        # -- bottom right --
        box = QVBoxLayout()
        frame = QFrame()
        frame.setLayout(box)
        splitter_bottom.addWidget(frame)
        box.addWidget(QLabel('Error'))
        box.addWidget(self.stderr)
        # -------
        splitter_main.addWidget(splitter_bottom)

        self.grid.addWidget(splitter_main, 0, 0)
        splitter_main.setSizes((self.screen.height() * 0.6, self.screen.height() * 0.4))
        splitter_bottom.setSizes((self.map.width / 2, self.map.width / 2, self.stderr.sizeHint().width()))
