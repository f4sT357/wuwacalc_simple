
import sys
from PyQt6.QtWidgets import QApplication, QDialog, QRubberBand
from PyQt6.QtCore import Qt, QRect, QPoint, QSize

class TestDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.resize(400, 300)
        self.setWindowTitle("RubberBand Test")
        
        self.origin = QPoint()
        self.rubberBand = QRubberBand(QRubberBand.Shape.Rectangle, self)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.pos()
            self.rubberBand.setGeometry(QRect(self.origin, QSize()))
            self.rubberBand.show()

    def mouseMoveEvent(self, event):
        if not self.origin.isNull():
            self.rubberBand.setGeometry(QRect(self.origin, event.pos()).normalized())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pass

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Mimic the app's stylesheet
    # "QWidget { background-color: ... }"
    # Let's use a dark gray background for widgets
    app.setStyleSheet("""
        QWidget { background-color: #333333; color: white; }
    """)
    
    dlg = TestDialog()
    dlg.show()
    
    sys.exit(app.exec())
