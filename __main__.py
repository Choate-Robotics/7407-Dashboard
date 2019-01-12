import os, sys
sys.path.append(os.path.join(os.path.dirname(__file__),'..'))

from PySide2.QtWidgets import QApplication
from dashboard import Simulator

if __name__=='__main__':
    app = QApplication([])
    app.setStyle('Fusion')
    
    sim = Simulator()
    sim.setWindowTitle('7407 Dashboard')
    sim.showFullScreen()
    
    sys.stdout = sim.stdout
    sys.stderr = sim.stderr
    
    sim.show()
    status = app.exec_()
    exit(status)
