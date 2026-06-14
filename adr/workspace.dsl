workspace "CHT ToolBench Architecture" "Архитектура FreeCAD-плагина для проектирования, валидации, моделирования и документирования процессов химико-термической обработки стали." {
    !identifiers flat
    !impliedRelationships false

    model {
        engineer = person "Инженер-технолог" "Проектирует изделие и процесс ХТО, анализирует результат валидации, моделирования и отчёт." "External"

        freecad = softwareSystem "FreeCAD" "CAD-среда выполнения плагина, содержащая документ, твердотельную модель, дерево объектов, редактор свойств и 3D-представление." "External" {
            freecadDocument = container "FreeCAD Document Model" "Хранит CAD-геометрию, HeatTreatmentProcess, этапы и сохранённые результаты анализа." "FreeCAD Document API" "External"
            freecadViewer = container "FreeCAD 3D Viewer" "Показывает CAD-модель, выделенные грани и рёбра, а в будущем цветовую карту моделирования." "FreeCADGui / Coin3D" "External"
        }

        fileSystem = softwareSystem "Файловая система" "Принимает экспортируемые отчёты HTML, PDF или DOCX и связанные изображения." "External"

        chtToolBench = softwareSystem "CHT ToolBench" "FreeCAD Python Workbench для создания процесса ХТО, статической валидации и проектируемых функций моделирования и отчётности." {
            pluginRuntime = container "Plugin Runtime" "Регистрирует workbench и команды, управляет деревом процесса, выполняет валидацию и показывает результаты. [Implemented]" "Python, FreeCAD Python API, PySide" "Implemented" {
                workbenchLifecycle = component "Workbench Lifecycle" "Инициализирует toolbar/menu и обновляет восстановленные объекты процесса при активации workbench. [Implemented]" "InitGui.py" "Implemented"
                toolbarCommands = component "Toolbar Command Registry" "Регистрирует пять команд и маршрутизирует действия пользователя. Создание процесса, добавление этапа и валидация реализованы. [Implemented]" "toolbar.py" "Implemented"
                processTreeManager = component "Process Tree Manager" "Создаёт HeatTreatmentProcess и App::FeaturePython-этапы, свойства, proxy/view provider и порядок этапов. [Implemented]" "tree.py" "Implemented"
                validationUI = component "Validation UI" "Запускает валидацию, читает выделение FreeCAD и показывает таблицу сообщений с переходом к проблемному объекту. [Implemented]" "commands/validate_process.py, PySide" "Implemented"
                validationEngine = component "Validation Engine" "Координирует проверки модели, процесса, материала, параметров, целей и геометрических рисков. [Implemented]" "rule_engine/engine.py" "Implemented"
                rulesLoader = component "Rules Loader" "Читает и проверяет структуру rules.yaml, применяет strictness, включение правил и шаблоны сообщений. [Implemented]" "rule_engine/rules.py, PyYAML" "Implemented"
                freecadAdapter = component "FreeCAD Adapter" "Находит процесс и модель, разрешает материал, собирает этапы и вычисляет fingerprint входных данных. [Implemented]" "rule_engine/freecad_adapter.py" "Implemented"
                geometryAnalyzer = component "Geometry Analyzer" "Проверяет solid-геометрию OpenCascade и извлекает геометрические признаки и диагностические зоны. [Implemented]" "rule_engine/geometry.py, Part/OpenCascade" "Implemented"
                validationModels = component "Validation Models" "Определяет Severity, ValidationStatus, ValidationMessage, GeometryFacts и ValidationResult. [Implemented]" "rule_engine/models.py, dataclasses" "Implemented"
                resultPersistence = component "Result Persistence and Highlighting" "Сохраняет CHTValidationResult и формирует объекты подсветки ошибок и предупреждений в документе. [Implemented]" "rule_engine/freecad_adapter.py" "Implemented"
                simulationCommand = component "Simulation Command" "Проверяет наличие актуальной успешной валидации, после чего показывает сообщение-заглушку. [Stub]" "toolbar.py, commands/validate_process.py" "Stub"
                reportCommand = component "Report Command" "Показывает сообщение-заглушку; чтение результатов и построение отчёта отсутствуют. [Stub]" "toolbar.py" "Stub"
            }

            rulesConfig = container "Validation Rules" "Конфигурация правил процесса, этапов, материалов, целевых параметров, геометрии и уровней строгости. [Implemented]" "YAML (rule_engine/rules.yaml)" "Implemented"
            simulationEngine = container "Simulation Engine" "Будущий расчёт глубины слоя, твёрдости и рисков с классификацией и визуализацией зон модели. [Planned]" "Python, FreeCAD API" "Planned"
            reportGenerator = container "Report Generator" "Будущее построение таблиц, графиков, итоговой оценки, окна просмотра и экспорта отчёта. [Planned]" "Python, PySide, HTML/plotting" "Planned"
        }

        engineer -> freecad "Создаёт, импортирует и редактирует твердотельную CAD-модель"
        engineer -> chtToolBench "Создаёт и редактирует процесс ХТО, запускает анализ и изучает результаты"
        chtToolBench -> freecad "Работает внутри FreeCAD и читает/дополняет активный документ" "FreeCAD Python API"
        chtToolBench -> fileSystem "Экспортирует сформированный отчёт" "HTML/PDF/DOCX" "Planned"

        engineer -> pluginRuntime "Использует команды CHT Tools и окна результатов" "FreeCAD GUI"
        pluginRuntime -> freecadDocument "Читает CAD-модель и сохраняет процесс, этапы и результаты" "FreeCAD Document API"
        pluginRuntime -> freecadViewer "Выделяет проблемные грани/рёбра и управляет отображением" "FreeCADGui"
        pluginRuntime -> rulesConfig "Загружает правила статической валидации" "YAML"
        pluginRuntime -> simulationEngine "Передаёт актуальные модель, материал и процесс после проверки fingerprint" "Python API" "Planned"
        pluginRuntime -> reportGenerator "Запрашивает отчёт по последнему результату моделирования" "Python API" "Planned"
        simulationEngine -> rulesConfig "Читает расчётные коэффициенты и пороги риска" "YAML" "Planned"
        simulationEngine -> freecadDocument "Читает входные данные и сохраняет SimulationResult" "FreeCAD Document API" "Planned"
        simulationEngine -> freecadViewer "Отображает цветовую карту и легенду зон" "FreeCADGui / Coin3D" "Planned"
        reportGenerator -> freecadDocument "Читает сохранённые параметры процесса и SimulationResult" "FreeCAD Document API" "Planned"
        reportGenerator -> fileSystem "Сохраняет отчёт и изображения" "HTML/PDF/DOCX" "Planned"

        engineer -> toolbarCommands "Нажимает команды toolbar/menu" "FreeCAD GUI"
        workbenchLifecycle -> toolbarCommands "Регистрирует команды при Initialize()"
        workbenchLifecycle -> processTreeManager "Обновляет proxy восстановленных этапов при Activated()"
        toolbarCommands -> processTreeManager "Создаёт процесс и добавляет выбранный этап"
        toolbarCommands -> validationUI "Запускает команду «Валидировать»"
        toolbarCommands -> simulationCommand "Передаёт команду «Запустить моделирование»"
        toolbarCommands -> reportCommand "Передаёт команду «Отчёт»"
        validationUI -> validationEngine "Вызывает validate(document, selection)"
        validationUI -> freecad "Получает выделение и показывает PySide-диалог результата" "FreeCADGui / PySide"
        validationEngine -> rulesLoader "Запрашивает RuleBook"
        rulesLoader -> rulesConfig "Читает и валидирует конфигурацию" "UTF-8 YAML"
        validationEngine -> freecadAdapter "Разрешает модель, процесс, материал, этапы и fingerprint"
        validationEngine -> geometryAnalyzer "Запрашивает GeometryFacts и геометрические диагностики"
        validationEngine -> validationModels "Формирует сообщения и итоговый ValidationResult"
        validationEngine -> resultPersistence "Передаёт результат для сохранения и подсветки"
        freecadAdapter -> freecad "Читает объекты документа и BREP-представление" "FreeCAD/Part API"
        geometryAnalyzer -> freecad "Анализирует Shape, Faces, Edges и Solids" "Part/OpenCascade"
        resultPersistence -> freecad "Создаёт CHTValidationResult и объекты подсветки" "FreeCAD/Part API"
        simulationCommand -> validationEngine "Вызывает can_simulate() для проверки статуса и fingerprint"
        simulationCommand -> simulationEngine "Запускает расчёт после успешной проверки" "Python API" "Planned"
        reportCommand -> reportGenerator "Запрашивает просмотр или экспорт отчёта" "Python API" "Planned"
    }

    !adrs .

    views {
        !include 001-c4-context.dsl
        !include 002-c4-container.dsl
        !include 003-c4-component.dsl

        styles {
            element "Person" {
                shape Person
            }

            element "External" {
                background #1168BD
                color #FFFFFF
                stroke #0B4884
            }

            element "Implemented" {
                background #2E7D32
                color #FFFFFF
                stroke #1B5E20
            }

            element "Stub" {
                background #F9A825
                color #1F1F1F
                stroke #8D6E00
            }

            element "Planned" {
                background #ECEFF1
                color #455A64
                stroke #78909C
                border dashed
            }

            element "Container" {
                shape RoundedBox
            }

            element "Component" {
                shape Component
            }

            relationship "Relationship" {
                color #546E7A
                routing Orthogonal
            }

            relationship "Planned" {
                color #90A4AE
                style dashed
            }
        }

        properties {
            "plantuml.url" "https://plantuml.com/plantuml"
            "plantuml.format" "svg"
        }
    }

    !plugin com.structurizr.dsl.plugin.documentation.PlantUML

    configuration {
        scope none
    }
}
