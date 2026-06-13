import FreeCAD
import FreeCADGui

from rule_engine.engine import ValidationEngine
from rule_engine.models import Severity, ValidationResult, ValidationStatus


STATUS_TEXT = {
    ValidationStatus.VALID: "Процесс ХТО валиден",
    ValidationStatus.VALID_WITH_WARNINGS: "Процесс ХТО валиден с предупреждениями",
    ValidationStatus.INVALID: "Процесс ХТО содержит ошибки",
    ValidationStatus.VALIDATION_FAILED: "Валидация не выполнена",
}


def _qt_modules():
    try:
        from PySide import QtCore, QtGui

        return QtCore, QtGui
    except ImportError:
        from PySide6 import QtCore, QtWidgets

        return QtCore, QtWidgets


def _selection():
    try:
        return FreeCADGui.Selection.getSelectionEx()
    except Exception:
        return []


def _show_error(title: str, message: str) -> None:
    FreeCAD.Console.PrintError("{0}: {1}\n".format(title, message))
    try:
        _, QtGui = _qt_modules()
        QtGui.QMessageBox.critical(None, title, message)
    except Exception:
        pass


class ValidationResultsDialog:
    def __init__(self, result: ValidationResult, document):
        QtCore, QtGui = _qt_modules()
        self._QtCore = QtCore
        self._QtGui = QtGui
        self.result = result
        self.document = document

        self.dialog = QtGui.QDialog()
        self.dialog.setWindowTitle("Результат валидации ХТО")
        self.dialog.resize(980, 620)

        layout = QtGui.QVBoxLayout(self.dialog)
        status = QtGui.QLabel(
            "<b>{0}</b>".format(STATUS_TEXT.get(result.status, result.status.value))
        )
        layout.addWidget(status)

        counters = QtGui.QLabel(
            "Ошибки: {0}    Предупреждения: {1}    Информация: {2}".format(
                result.error_count,
                result.warning_count,
                result.info_count,
            )
        )
        layout.addWidget(counters)

        if result.material or result.model_name:
            context = QtGui.QLabel(
                "Модель: {0}    Материал: {1}".format(
                    result.model_name or "не определена",
                    result.material or "не определён",
                )
            )
            layout.addWidget(context)

        self.table = QtGui.QTableWidget(len(result.messages), 4)
        self.table.setHorizontalHeaderLabels(
            ["Код", "Уровень", "Проблема", "Объект"]
        )
        self.table.setSelectionBehavior(
            QtGui.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setEditTriggers(
            QtGui.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.verticalHeader().setVisible(False)

        for row, message in enumerate(result.messages):
            values = (
                message.code,
                message.severity.value,
                message.problem,
                message.object_reference,
            )
            for column, value in enumerate(values):
                item = QtGui.QTableWidgetItem(str(value))
                if message.severity == Severity.ERROR:
                    item.setForeground(QtGui.QColor(190, 40, 40))
                elif message.severity == Severity.WARNING:
                    item.setForeground(QtGui.QColor(180, 115, 0))
                self.table.setItem(row, column, item)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QtGui.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QtGui.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QtGui.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QtGui.QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)

        self.details = QtGui.QTextEdit()
        self.details.setReadOnly(True)
        self.details.setMinimumHeight(150)
        layout.addWidget(self.details)

        buttons = QtGui.QDialogButtonBox(
            QtGui.QDialogButtonBox.StandardButton.Close
        )
        buttons.rejected.connect(self.dialog.reject)
        buttons.accepted.connect(self.dialog.accept)
        layout.addWidget(buttons)

        self.table.currentCellChanged.connect(self._row_changed)
        if result.messages:
            self.table.selectRow(0)
            self._show_message(0)
        else:
            self.details.setPlainText(
                "Нарушения не обнаружены. Процесс готов к моделированию."
            )

    def _row_changed(self, current_row, _current_column, _previous_row, _previous_column):
        self._show_message(current_row)

    def _show_message(self, row):
        if row < 0 or row >= len(self.result.messages):
            return
        message = self.result.messages[row]
        self.details.setPlainText(
            "[{0}] {1}\n\nПроблема: {2}\n\nПричина: {3}\n\n"
            "Рекомендация: {4}\n\nОбъект: {5}".format(
                message.code,
                message.severity.value,
                message.problem,
                message.cause,
                message.recommendation,
                message.object_reference or "не указан",
            )
        )
        self._select_reference(message)

    def _select_reference(self, message):
        if not message.object_name or self.document is None:
            return
        try:
            FreeCADGui.Selection.clearSelection()
            if message.subelements:
                for subelement in message.subelements:
                    FreeCADGui.Selection.addSelection(
                        self.document.Name,
                        message.object_name,
                        subelement,
                    )
            else:
                FreeCADGui.Selection.addSelection(
                    self.document.Name, message.object_name
                )
        except Exception:
            pass

    def exec(self):
        if hasattr(self.dialog, "exec"):
            return self.dialog.exec()
        return self.dialog.exec_()


def run_validation(document=None, selection=None, show_dialog=True):
    document = document or FreeCAD.ActiveDocument
    try:
        result = ValidationEngine().validate(
            document,
            _selection() if selection is None else selection,
        )
    except Exception as exc:
        _show_error(
            "Валидация ХТО",
            "Внутренняя ошибка валидации: {0}".format(exc),
        )
        return None

    FreeCAD.Console.PrintMessage(
        "CHT validation: {0}; errors={1}; warnings={2}; info={3}\n".format(
            result.status.value,
            result.error_count,
            result.warning_count,
            result.info_count,
        )
    )
    if show_dialog:
        try:
            ValidationResultsDialog(result, document).exec()
        except Exception as exc:
            _show_error(
                "Результат валидации",
                "Не удалось открыть окно результата: {0}".format(exc),
            )
    return result


def simulation_allowed(document=None, selection=None):
    document = document or FreeCAD.ActiveDocument
    return ValidationEngine().can_simulate(
        document,
        _selection() if selection is None else selection,
    )


class ValidateProcess:
    def Activated(self):
        run_validation()

    def GetResources(self):
        return {
            "MenuText": "Валидировать",
            "ToolTip": "Проверить процесс ХТО",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None
