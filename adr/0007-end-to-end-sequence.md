# 7. Sequence полного пользовательского пути

Date: 2026-06-14

## Status

Accepted

## Context

Диаграмма объединяет создание процесса, добавление этапов, цикл валидации, проверку актуальности результата и проектируемое продолжение через моделирование и отчёт.

## Decision

```plantuml
@startuml
title Sequence — полный путь от CAD-модели до отчёта
autonumber
hide footbox
skinparam shadowing false
skinparam sequence {
  ArrowColor #546E7A
  LifeLineBorderColor #78909C
  LifeLineBackgroundColor #FFFFFF
  ParticipantBorderColor #455A64
  ParticipantBackgroundColor #E8F5E9
  ActorBorderColor #455A64
  ActorBackgroundColor #FFFFFF
}

actor "Инженер" as User
participant "FreeCAD GUI" as FreeCAD

box "Implemented" #E8F5E9
participant "CHTWorkbench" as Workbench
participant "Toolbar Commands" as Toolbar
participant "Process Tree\nManager" as Tree
participant "Validation UI" as ValidationUI
participant "ValidationEngine" as Engine
participant "Rules Loader" as Rules
database "rules.yaml" as RulesYaml
participant "FreeCAD Adapter" as Adapter
participant "Geometry Analyzer" as Geometry
database "FreeCAD Document" as Document
participant "Validation Dialog" as Dialog
end box

box "Stub / Planned" #ECEFF1
participant "Simulation Command\n<<Stub>>" as SimCommand #FFF8E1
participant "Simulation Engine\n<<Planned>>" as SimEngine #ECEFF1
participant "3D Viewer\n<<Planned result>>" as Viewer #ECEFF1
participant "Report Command\n<<Stub>>" as ReportCommand #FFF8E1
participant "Report Generator\n<<Planned>>" as ReportGenerator #ECEFF1
database "Report File\n<<Planned>>" as ReportFile #ECEFF1
end box

User -> FreeCAD : создаёт/импортирует solid и выбирает модель
FreeCAD -> Workbench : Initialize()
Workbench -> Toolbar : register_commands()
Workbench -> FreeCAD : appendToolbar()/appendMenu()
FreeCAD -> Workbench : Activated()
Workbench -> Tree : upgrade_process_objects(ActiveDocument)
Tree -> Document : восстановить StageProxy/ViewProvider

User -> Toolbar : «Создать процесс»
Toolbar -> Tree : ensure_default_process_tree()
Tree -> Document : найти/создать HeatTreatmentProcess
Tree -> Document : назначить TargetObject/TargetPart
Tree -> Document : добавить отсутствующие стандартные этапы\nHeating, Cementation, Quenching, Tempering
Tree -> Document : recompute()
Tree --> Toolbar : process
Toolbar -> FreeCAD : показать сообщение об успехе

loop Добавление или редактирование этапов
  User -> Toolbar : «Добавить этап»
  Toolbar -> Tree : get_stage_names()
  Toolbar -> FreeCAD : QInputDialog со списком STAGE_LIBRARY
  User --> Toolbar : выбранный тип или отмена
  alt тип выбран
    Toolbar -> Tree : add_stage_to_process(stage_name)
    Tree -> Document : ensure_process_group()
    Tree -> Document : создать App::FeaturePython,\nназначить properties/proxy/SequenceNumber
    Tree -> Document : recompute()
    Toolbar -> FreeCAD : показать сообщение об успехе
  else операция отменена
    Toolbar -> FreeCAD : показать сообщение об отмене
  end
  User -> FreeCAD : редактирует Data properties\nили удаляет этап штатным действием
end

loop Валидация и исправление
  User -> Toolbar : «Валидировать»
  Toolbar -> ValidationUI : run_validation()
  ValidationUI -> Tree : upgrade_process_objects(document)
  ValidationUI -> FreeCAD : Selection.getSelectionEx()
  ValidationUI -> Engine : validate(document, selection)

  Engine -> Adapter : find_process() + resolve_model()
  Engine -> Rules : load_rules()
  Rules -> RulesYaml : read_text(UTF-8) + yaml.safe_load()
  Rules --> Engine : RuleBook или RuleConfigurationError

  opt rules и model доступны
    Engine -> Geometry : analyze_geometry(model, geometry_rules)
    Geometry -> Document : прочитать Shape/Faces/Edges/Solids
    Geometry --> Engine : GeometryFacts + diagnostics
  end

  Engine -> Adapter : resolve_material() + collect_stages()
  Adapter -> Document : прочитать process/model properties
  Adapter --> Engine : material + ordered stages
  Engine -> Engine : проверить обязательные этапы и порядок
  Engine -> Engine : проверить required/ranges/allowed values
  Engine -> Engine : проверить материал, цели и геометрические риски
  Engine -> Adapter : compute_fingerprint(model, process, rules text)
  Adapter -> Document : экспортировать BREP и snapshot properties
  Adapter --> Engine : SHA-256 fingerprint
  Engine -> Engine : ValidationResult.from_messages()
  Engine -> Adapter : persist_result() + update_highlights()
  Adapter -> Document : записать CHTValidationResult\nи объекты Error/Warning highlights
  Engine --> ValidationUI : ValidationResult
  ValidationUI -> Dialog : показать status, counters, messages, details

  opt пользователь выбирает сообщение
    Dialog -> FreeCAD : clearSelection()/addSelection(object, subelements)
  end

  alt INVALID или VALIDATION_FAILED
    Dialog --> User : ошибки, причины и рекомендации
    User -> FreeCAD : исправляет модель/процесс/rules.yaml
  else VALID_WITH_WARNINGS
    Dialog --> User : результат допустим с предупреждениями
  else VALID
    Dialog --> User : процесс валиден
  end
end

User -> Toolbar : «Запустить моделирование»
Toolbar -> SimCommand : Activated()
SimCommand -> Engine : can_simulate(document, selection)
Engine -> Adapter : read_saved_status()
Adapter -> Document : прочитать ValidationStatus/InputFingerprint
Engine -> Rules : load_rules()
Engine -> Adapter : resolve_model()/find_process()\ncompute_fingerprint()
Adapter -> Document : прочитать текущие model/process/stages
Engine --> SimCommand : allowed + reason

alt результата нет, status недопустим или fingerprint изменился
  SimCommand -> FreeCAD : warning: моделирование заблокировано
else актуальная VALID/VALID_WITH_WARNINGS
  SimCommand -> FreeCAD : текущее сообщение-заглушка
  note right of SimCommand
    На этом существующий код заканчивается.
    Следующие сообщения описывают planned-поведение.
  end note
  SimCommand -[#9E9E9E]> SimEngine : planned: simulate(model, process, material)
  SimEngine -[#9E9E9E]> Document : прочитать геометрию и параметры
  SimEngine -[#9E9E9E]> SimEngine : рассчитать глубину, твёрдость и риски\nклассифицировать зоны
  SimEngine -[#9E9E9E]> Viewer : показать цветовую карту и легенду
  SimEngine -[#9E9E9E]> Document : сохранить SimulationResult
  SimEngine -[#9E9E9E]> User : показать краткую сводку
end

User -> Toolbar : «Отчёт»
Toolbar -> ReportCommand : Activated()
ReportCommand -> FreeCAD : текущее сообщение-заглушка
note right of ReportCommand
  Проверка SimulationResult и формирование
  отчёта в существующем коде отсутствуют.
end note
ReportCommand -[#9E9E9E]> ReportGenerator : planned: build(last SimulationResult)
ReportGenerator -[#9E9E9E]> Document : прочитать процесс, расчёты и zones
ReportGenerator -[#9E9E9E]> ReportGenerator : построить таблицы, оценку,\nрекомендации и четыре графика
ReportGenerator -[#9E9E9E]> User : открыть окно предварительного просмотра

opt пользователь экспортирует отчёт
  User -[#9E9E9E]> ReportGenerator : выбрать формат и путь
  ReportGenerator -[#9E9E9E]> ReportFile : сохранить HTML/PDF/DOCX\nи изображения
  ReportGenerator -[#9E9E9E]> User : сообщить результат экспорта
end

legend right
  Зелёный блок: Implemented
  Жёлтый participant: Stub
  Серый participant/стрелка: Planned
endlegend
@enduml
```

## Consequences

Цикл валидации соответствует существующему коду. Planned-вызовы начинаются только после сообщения-заглушки `RunSimulationCommand` и после сообщения-заглушки `ReportCommand`. Изменение модели, процесса, этапов или текста `rules.yaml` после успешной валидации блокирует моделирование из-за нового fingerprint.
