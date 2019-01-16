from PySide2.QtWidgets import QWidget, QDesktopWidget
from PySide2.QtGui import QPainter,QColor,QFont
from field_map.map import FieldMap

class Minimap(QWidget):
    def __init__(self):
        super().__init__()
        self.map = FieldMap()
        self.setMouseTracking(True)
        self.hover_x = 0
        self.hover_y = 0
        self.showCoordinate = False
        self.scale = QDesktopWidget().screenGeometry().height() * 0.6 / self.map.width
        self.width = self.map.length * self.scale
        self.height = self.map.width * self.scale
        self.setFixedSize(self.width, self.height)
        self.zoom = 1
    
    def paintEvent(self, event):
        qp = QPainter()
        qp.begin(self)
        try:
            self.paintMap(qp)
        finally:
            qp.end()
    
    def mouseMoveEvent(self, event):
        self.hover_x = event.x()
        self.hover_y = event.y()
        self.repaint()
    
    def enterEvent(self, event):
        self.showCoordinate = True
    
    def leaveEvent(self, event):
        self.showCoordinate = False
        self.repaint()
    
    def paintMap(self, qp):
        rect = self.rect()
        qp.setBrush(QColor(255, 255, 255))
        assert rect.x() == 0
        assert rect.y() == 0
        scaled_origin_x = rect.x()
        scaled_origin_y = rect.y()
        qp.drawRect(scaled_origin_x, scaled_origin_y, self.width, self.height)
        
        if self.showCoordinate:
            if self.hover_x < self.width and self.hover_y < scaled_origin_y + self.height:
                qp.drawText(QFont().pointSize(), QFont().pointSize() * 2,  # 1em offset from both sides
                            f"{round(self.hover_x/self.scale,2)},{round((rect.height()-self.hover_y)/self.scale,2)}")
        
        # TODO: draw axis
        # TODO: implement zoom slide bar

