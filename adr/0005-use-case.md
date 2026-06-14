# 5. Use Case всей системы CHT ToolBench

Date: 2026-06-14

## Status

Accepted

## Context

Диаграмма показывает полный функциональный контур плагина с точки зрения инженера-технолога, включая реализованные функции, зарегистрированные заглушки и проектируемые сценарии.

## Decision

```plantuml
@startuml
title Use Case — CHT ToolBench
left to right direction
skinparam shadowing false
skinparam packageStyle rectangle
skinparam usecase {
  BackgroundColor #E8F5E9
  BorderColor #2E7D32
  BackgroundColor<<Stub>> #FFF8E1
  BorderColor<<Stub>> #F9A825
  BackgroundColor<<Planned>> #ECEFF1
  BorderColor<<Planned>> #78909C
}

actor "Инженер-технолог" as Engineer
actor "FreeCAD" as FreeCAD
actor "Файловая система" as FileSystem

rectangle "CHT ToolBench" {
  usecase "Создать процесс ХТО" as UC_Create
  usecase "Связать процесс\nс CAD-моделью" as UC_Link
  usecase "Редактировать параметры\nпроцесса и этапов" as UC_Edit
  usecase "Добавить этап" as UC_Add
  usecase "Удалить этап" as UC_Delete
  usecase "Валидировать процесс" as UC_Validate
  usecase "Проверить геометрию,\nматериал и этапы" as UC_Checks
  usecase "Просмотреть ошибки,\nпричины и рекомендации" as UC_Messages
  usecase "Выделить проблемную\nгрань или ребро" as UC_Select
  usecase "Показать зоны ошибок\nи предупреждений" as UC_Highlight
  usecase "Проверить готовность\nк моделированию" as UC_Gate

  usecase "Запустить моделирование" as UC_Sim <<Stub>>
  usecase "Рассчитать глубину слоя,\nтвёрдость и риски" as UC_Calc <<Planned>>
  usecase "Показать цветовую карту,\nлегенду и сведения о зоне" as UC_Color <<Planned>>
  usecase "Сбросить или переключить\nвизуализацию" as UC_ViewMode <<Planned>>
  usecase "Сохранить результат\nмоделирования" as UC_SaveSim <<Planned>>

  usecase "Открыть отчёт" as UC_Report <<Stub>>
  usecase "Сформировать таблицы,\nоценку и рекомендации" as UC_ReportData <<Planned>>
  usecase "Построить графики" as UC_Charts <<Planned>>
  usecase "Добавить снимок модели\nи сводку зон риска" as UC_Snapshot <<Planned>>
  usecase "Экспортировать отчёт" as UC_Export <<Planned>>
}

Engineer --> UC_Create
Engineer --> UC_Edit
Engineer --> UC_Add
Engineer --> UC_Delete
Engineer --> UC_Validate
Engineer --> UC_Messages
Engineer --> UC_Sim
Engineer --> UC_Report
Engineer --> UC_ViewMode
Engineer --> UC_Export

UC_Create ..> UC_Link : <<include>>
UC_Validate ..> UC_Checks : <<include>>
UC_Validate ..> UC_Highlight : <<include>>
UC_Messages ..> UC_Select : <<extend>>
UC_Sim ..> UC_Gate : <<include>>
UC_Sim ..[#9E9E9E,dashed]> UC_Calc : <<include>> planned
UC_Calc ..[#9E9E9E,dashed]> UC_Color : <<include>>
UC_Calc ..[#9E9E9E,dashed]> UC_SaveSim : <<include>>
UC_Report ..[#9E9E9E,dashed]> UC_ReportData : <<include>> planned
UC_ReportData ..[#9E9E9E,dashed]> UC_Charts : <<include>>
UC_ReportData ..[#9E9E9E,dashed]> UC_Snapshot : <<include>>
UC_Export ..[#9E9E9E,dashed]> UC_Report : <<extend>>

FreeCAD --> UC_Link
FreeCAD --> UC_Edit
FreeCAD --> UC_Checks
FreeCAD --> UC_Select
FreeCAD --> UC_Highlight
FreeCAD --> UC_Color
FreeCAD --> UC_Snapshot
FileSystem --> UC_Export

note right of UC_Create
  Фактическая команда переиспользует существующий
  HeatTreatmentProcess и добавляет отсутствующие
  стандартные этапы. При отсутствии документа
  tree.py создаёт новый документ автоматически.
end note

note right of UC_Add
  Типы и defaults берутся из STAGE_LIBRARY.
  Этап всегда добавляется в конец; выбор позиции
  и загрузка каталога этапов из rules.yaml отсутствуют.
end note

note right of UC_Gate
  Реализованы проверка сохранённого статуса
  и сравнение SHA-256 fingerprint модели,
  процесса, этапов и текста rules.yaml.
end note

note bottom of UC_Report
  В текущем коде отчёт не проверяет наличие
  SimulationResult и показывает только заглушку.
end note

legend right
  |= Цвет |= Статус |
  |<#E8F5E9> зелёный | Implemented |
  |<#FFF8E1> жёлтый | Stub |
  |<#ECEFF1> серый | Planned |
endlegend
@enduml
```

## Consequences

Use cases моделирования, цветовой карты, формирования и экспорта отчёта являются целевым поведением из `memorybank/`, а не описанием существующей реализации. Удаление этапа уже возможно штатным удалением объекта FreeCAD через `StageViewProvider`, хотя отдельной toolbar-команды для него нет.
