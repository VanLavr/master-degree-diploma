import FreeCADGui
import FreeCAD

class CHTWorkbench(FreeCADGui.Workbench):
    MenuText = "CHT CAD"
    ToolTip = "Chemical Heat Treatment Validation"

    def Initialize(self):
        try:
            import toolbar

            commands = toolbar.register_commands()
        except Exception as exc:
            FreeCAD.Console.PrintError(
                "CHT Workbench initialization failed while loading toolbar: {0}\n".format(exc)
            )
            raise

        self.appendToolbar("CHT Tools", commands)
        self.appendMenu("CHT CAD", commands)
        FreeCAD.Console.PrintMessage("CHT Workbench loaded!\n")

    def Activated(self):
        try:
            import tree

            tree.upgrade_process_objects(FreeCAD.ActiveDocument)
        except Exception as exc:
            FreeCAD.Console.PrintWarning(
                "CHT object upgrade failed: {0}\n".format(exc)
            )

FreeCADGui.addWorkbench(CHTWorkbench())
