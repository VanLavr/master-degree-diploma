import FreeCAD
import FreeCADGui

import tree


COMMANDS = [
    "CHT_CreateProcess",
    "CHT_AddStage",
    "CHT_RunSimulation",
    "CHT_Validate",
    "CHT_Report",
]


def _show_action_feedback(title: str, message: str) -> None:
    FreeCAD.Console.PrintMessage(f"{title}: {message}\n")

    try:
        from PySide import QtGui

        QtGui.QMessageBox.information(None, title, message)
    except Exception:
        # If Qt is unavailable during startup, console logging is enough.
        pass


def _select_stage_type():
    stage_names = tree.get_stage_names()

    try:
        from PySide import QtGui

        selected, accepted = QtGui.QInputDialog.getItem(
            None,
            "\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u044d\u0442\u0430\u043f",
            "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0442\u0438\u043f \u044d\u0442\u0430\u043f\u0430:",
            stage_names,
            0,
            False,
        )
        if not accepted:
            return None
        return str(selected)
    except Exception:
        return stage_names[0] if stage_names else None


class _BaseCommand:
    name = ""
    tooltip = ""
    message = ""

    def GetResources(self):
        return {
            "MenuText": self.name,
            "ToolTip": self.tooltip,
        }

    def Activated(self):
        _show_action_feedback(self.name, self.message)

    def IsActive(self):
        return True


class CreateProcessCommand(_BaseCommand):
    name = "\u0421\u043e\u0437\u0434\u0430\u0442\u044c \u043f\u0440\u043e\u0446\u0435\u0441\u0441"
    tooltip = (
        "\u0421\u043e\u0437\u0434\u0430\u0442\u044c \u043d\u043e\u0432\u044b\u0439 "
        "\u0442\u0435\u0445\u043f\u0440\u043e\u0446\u0435\u0441\u0441 "
        "\u0445\u0438\u043c\u0438\u043a\u043e-\u0442\u0435\u0440\u043c\u0438\u0447\u0435\u0441\u043a\u043e\u0439 "
        "\u043e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0438"
    )
    message = (
        "\u0421\u043e\u0437\u0434\u0430\u043d \u0443\u0437\u0435\u043b HeatTreatmentProcess "
        "\u0441 \u0442\u0438\u043f\u043e\u0432\u044b\u043c\u0438 \u044d\u0442\u0430\u043f\u0430\u043c\u0438 "
        "\u0432 \u0434\u0435\u0440\u0435\u0432\u0435 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430."
    )

    def Activated(self):
        process = tree.ensure_default_process_tree()
        if FreeCAD.ActiveDocument is not None:
            FreeCAD.ActiveDocument.recompute()
        _show_action_feedback(
            self.name,
            (
                "\u0421\u043e\u0437\u0434\u0430\u043d \u043f\u0440\u043e\u0446\u0435\u0441\u0441 "
                "\u0432 \u0434\u0435\u0440\u0435\u0432\u0435 Model: {0}"
            ).format(process.Label),
        )


class AddStageCommand(_BaseCommand):
    name = "\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u044d\u0442\u0430\u043f"
    tooltip = (
        "\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c \u044d\u0442\u0430\u043f "
        "\u043e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0438 \u0432 "
        "\u0442\u0435\u043a\u0443\u0449\u0438\u0439 \u0442\u0435\u0445\u043f\u0440\u043e\u0446\u0435\u0441\u0441"
    )
    message = (
        "\u0412 \u043f\u0440\u043e\u0446\u0435\u0441\u0441 \u0434\u043e\u0431\u0430\u0432\u043b\u044f\u0435\u0442\u0441\u044f "
        "\u043d\u043e\u0432\u044b\u0439 \u044d\u0442\u0430\u043f \u0432 \u0434\u0435\u0440\u0435\u0432\u0435 FreeCAD."
    )

    def Activated(self):
        stage_name = _select_stage_type()
        if not stage_name:
            _show_action_feedback(
                self.name,
                "\u0414\u043e\u0431\u0430\u0432\u043b\u0435\u043d\u0438\u0435 \u044d\u0442\u0430\u043f\u0430 \u043e\u0442\u043c\u0435\u043d\u0435\u043d\u043e.",
            )
            return

        stage = tree.add_stage_to_process(stage_name)
        if FreeCAD.ActiveDocument is not None:
            FreeCAD.ActiveDocument.recompute()
        _show_action_feedback(
            self.name,
            "\u0414\u043e\u0431\u0430\u0432\u043b\u0435\u043d {0}".format(stage.Label),
        )


class RunSimulationCommand(_BaseCommand):
    name = (
        "\u0417\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c "
        "\u043c\u043e\u0434\u0435\u043b\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435"
    )
    tooltip = (
        "\u0417\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c "
        "\u043c\u043e\u0434\u0435\u043b\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435 "
        "\u0442\u0435\u0445\u043f\u0440\u043e\u0446\u0435\u0441\u0441\u0430 \u0434\u043b\u044f "
        "\u0432\u044b\u0431\u0440\u0430\u043d\u043d\u043e\u0439 \u0434\u0435\u0442\u0430\u043b\u0438"
    )
    message = (
        "\u0417\u0430\u043f\u0443\u0441\u043a "
        "\u043c\u043e\u0434\u0435\u043b\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u044f "
        "\u043f\u043e\u043a\u0430 \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442 \u043a\u0430\u043a "
        "\u0431\u0430\u0437\u043e\u0432\u0430\u044f \u0437\u0430\u0433\u043b\u0443\u0448\u043a\u0430 "
        "\u0438\u043d\u0442\u0435\u0440\u0444\u0435\u0439\u0441\u0430."
    )


class ValidateCommand(_BaseCommand):
    name = "\u0412\u0430\u043b\u0438\u0434\u0438\u0440\u043e\u0432\u0430\u0442\u044c"
    tooltip = (
        "\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c "
        "\u0442\u0435\u0445\u043f\u0440\u043e\u0446\u0435\u0441\u0441 "
        "\u043f\u0440\u0430\u0432\u0438\u043b\u0430\u043c\u0438 \u0438 "
        "\u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u044f\u043c\u0438"
    )
    message = (
        "\u0412\u0430\u043b\u0438\u0434\u0430\u0446\u0438\u044f \u043f\u043e\u043a\u0430 "
        "\u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442 \u043a\u0430\u043a "
        "\u0431\u0430\u0437\u043e\u0432\u0430\u044f \u0437\u0430\u0433\u043b\u0443\u0448\u043a\u0430 "
        "\u0438\u043d\u0442\u0435\u0440\u0444\u0435\u0439\u0441\u0430."
    )


class ReportCommand(_BaseCommand):
    name = "\u041e\u0442\u0447\u0451\u0442"
    tooltip = (
        "\u0421\u0444\u043e\u0440\u043c\u0438\u0440\u043e\u0432\u0430\u0442\u044c "
        "\u043e\u0442\u0447\u0451\u0442 \u043f\u043e "
        "\u0442\u0435\u0445\u043f\u0440\u043e\u0446\u0435\u0441\u0441\u0443 \u0438 "
        "\u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u0430\u043c "
        "\u0430\u043d\u0430\u043b\u0438\u0437\u0430"
    )
    message = (
        "\u0424\u043e\u0440\u043c\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435 "
        "\u043e\u0442\u0447\u0451\u0442\u0430 \u043f\u043e\u043a\u0430 "
        "\u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442 \u043a\u0430\u043a "
        "\u0431\u0430\u0437\u043e\u0432\u0430\u044f \u0437\u0430\u0433\u043b\u0443\u0448\u043a\u0430 "
        "\u0438\u043d\u0442\u0435\u0440\u0444\u0435\u0439\u0441\u0430."
    )


def register_commands():
    FreeCADGui.addCommand("CHT_CreateProcess", CreateProcessCommand())
    FreeCADGui.addCommand("CHT_AddStage", AddStageCommand())
    FreeCADGui.addCommand("CHT_RunSimulation", RunSimulationCommand())
    FreeCADGui.addCommand("CHT_Validate", ValidateCommand())
    FreeCADGui.addCommand("CHT_Report", ReportCommand())
    return COMMANDS
