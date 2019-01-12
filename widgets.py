from PySide2.QtWidgets import (QMainWindow,
                               QWidget,
                               QFrame,
                               QDesktopWidget,
                               QGridLayout,
                               QLabel,
                               QTextEdit,
                               QPlainTextEdit,
                               QSplitter,
                               QSizePolicy,
                               QSlider,
                               QVBoxLayout,
                               QHBoxLayout)

from PySide2.QtGui import (QPainter,
                           QColor,
                           QTextCursor,
                           QFont)

import sys
import traceback
from PySide2.QtCore import Qt
from field_map.map import FieldMap

class StreamOutput(QTextEdit):
    def __init__(self):
        super().__init__()
        self.setLineWrapMode(QTextEdit.NoWrap)
        self.setReadOnly(True)
        self.setTabStopWidth(4)
    
    def write(self, text, color=None):
        self.moveCursor(QTextCursor.End)
        if self.textCursor().columnNumber() == 0:
            self.insertHtml(f"<font color='grey'>{datetime.datetime.now().strftime('%H:%M:%S.%f')}</font> ")
        text = text.replace('\n', '<br>').replace(' ', '&nbsp;')
        if color:
            text = "<font color='%s'>" % color + text + '</font>'
        self.insertHtml(text)
    
    def flush(self):
        pass

class StreamError(StreamOutput):
    def write(self, text):
        self.moveCursor(QTextCursor.End)
        text = text.replace('\n', '<br>').replace(' ', '&nbsp;').replace('\t', '&nbsp;' * 4)
        self.insertHtml(f"<font color='red'>{text}</font>")


class StreamInput(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.insertPlainText('>>> ')
        self.document().clearUndoRedoStacks()
        self.cursorPositionChanged.connect(self.validateCursorPosition)
        self.lastCursorPosition = 4
        self.historyNumber = 0
        self.overrideCursorValidation = False
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            last_line = self.toPlainText().split('\n')[-1][4:]
            if not last_line.rstrip():
                self.moveCursor(QTextCursor.End)
                self.insertPlainText('\n>>> ')
                self.historyNumber = 0
                return
            print(f"<b>(exec)</b> {last_line}")
            try:
                exec(last_line, globals())
            except BaseException as e:
                tb = traceback.format_exc().replace(' ', '&nbsp;')
                sys.stdout.write(f"<br>{tb}", 'red')
            self.moveCursor(QTextCursor.End)
            self.insertPlainText('\n>>> ')
            self.historyNumber = 0
            self.document().clearUndoRedoStacks()
            return
        if event.key() == Qt.Key_Delete or event.key() == Qt.Key_Backspace:
            if self.textCursor().columnNumber() <= 4:
                return
        if event.key() == Qt.Key_Up:
            if self.historyNumber < self.document().blockCount() - 1:
                self.historyNumber += 1
                self.insertHistory()
            return
        
        if event.key() == Qt.Key_Down:
            if self.historyNumber > 1:
                self.historyNumber -= 1
                self.insertHistory()
            return
        
        super().keyPressEvent(event)
    
    def validateCursorPosition(self):
        cursor = self.textCursor()
        if cursor.block().blockNumber() != self.document().blockCount() - 1 or cursor.columnNumber() < 4:
            if not self.overrideCursorValidation:
                cursor.setPosition(self.lastCursorPosition)
                self.setTextCursor(cursor)
        else:
            self.lastCursorPosition = cursor.position()
    
    def insertHistory(self):
        document = self.document()
        block = document.findBlockByNumber(document.blockCount() - self.historyNumber - 1)
        self.overrideCursorValidation = True
        self.moveCursor(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
        self.textCursor().removeSelectedText()
        self.insertPlainText(block.text())
        self.moveCursor(QTextCursor.End)
        self.overrideCursorValidation = False


class SimulatedFieldMap(QWidget):
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
        

