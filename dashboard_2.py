import sys
from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
from widgets import StreamError, StreamInput, StreamOutput

class MyTableWidget(QWidget):
    def __init__(self, parent):
        super(QWidget, self).__init__(parent)
        self.layout = QVBoxLayout(self)

        # Initialize tab screen
        self.tabs = QTabWidget()
        self.tab1 = QWidget()
        self.tab2 = QWidget()
        self.tabs.resize(300,200)

        # Add tabs
        self.tabs.addTab(self.tab1,"Tab 1")
        self.tabs.addTab(self.tab2,"Tab 2")

        # Create first tab
        self.tab1.layout = QVBoxLayout(self)
        self.pushButton1 = QPushButton("PyQt5 button")
        self.tab1.layout.addWidget(self.pushButton1)
        self.tab1.setLayout(self.tab1.layout)

        # Add tabs to widget
        self.layout.addWidget(self.tabs)
        self.setLayout(self.layout)

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

        self.table_widget = MyTableWidget(self)
        self.setCentralWidget(self.table_widget)
