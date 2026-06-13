import FreeCADGui
import FreeCAD

class ValidateProcess:
    def Activated(self):
        print("Running validation...")

FreeCADGui.addCommand("ValidateProcess", ValidateProcess())