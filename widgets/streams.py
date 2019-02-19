import sys
import traceback
import datetime

from PySide2.QtCore import Qt
from PySide2.QtGui import (QColor, QFont, QPainter, QTextCursor)
from PySide2.QtWidgets import (QDesktopWidget, QPlainTextEdit, QTextEdit, QWidget)



class StreamOutput(QTextEdit):
    def __init__(self):
        super().__init__()
        self.setLineWrapMode(QTextEdit.NoWrap)
        self.setReadOnly(True)
        self.setTabStopWidth(4)
    
    def write(self, text, color=None):
        self.moveCursor(QTextCursor.End)
        # if self.textCursor().columnNumber() == 0:
        #     self.insertHtml(f"<font color='grey'>{datetime.datetime.now().strftime('%H:%M:%S.%f')}</font> ")
        text = text.replace('\n', '<br>').replace(' ', '&nbsp;')
        if color:
            text = "<font color='%s'>" % color + text + '</font>'
        self.insertHtml(text)
    
    def flush(self):
        pass
    
    def closeStream(self):
        'write everything back'

class StreamError(StreamOutput):
    def write(self, text):
        self.moveCursor(QTextCursor.End)
        text = text.replace('\n', '<br>').replace(' ', '&nbsp;').replace('\t', '&nbsp;' * 4)
        self.insertHtml(f"<font color='red'>{text}</font>")


class StreamInput(QPlainTextEdit):
    def __init__(self,namespace:dict=None,plain_text_output=False):
        super().__init__()
        if namespace:
            globals().update(namespace)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.insertPlainText('>>> ')
        self.document().clearUndoRedoStacks()
        self.cursorPositionChanged.connect(self.validateCursorPosition)
        self.lastCursorPosition = 4
        self.historyNumber = 0
        self.overrideCursorValidation = False
        self.plainTextOutput=plain_text_output
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            last_line = self.toPlainText().split('\n')[-1][4:]
            if not last_line.rstrip():
                self.moveCursor(QTextCursor.End)
                self.insertPlainText('\n>>> ')
                self.historyNumber = 0
                return
            if self.plainTextOutput:
                print(f'(exec) {last_line}')
            else:
                print(f"<b>(exec)</b> {last_line}")
            try:
                exec(last_line, globals())
            except BaseException as e:
                if self.plainTextOutput:
                    sys.stdout.write(traceback.format_exc())
                else:
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



__all__=['StreamOutput','StreamInput','StreamError']
