# 6. State Chart жизненного цикла процесса ХТО

Date: 2026-06-14

## Status

Accepted

## Context

Состояние системы определяется наличием процесса, актуальностью входных данных и последним результатом валидации. Состояния моделирования и отчётности добавлены как проектируемое продолжение жизненного цикла.

## Decision

```plantuml
@startuml
title State Chart — жизненный цикл процесса ХТО
hide empty description
skinparam shadowing false
skinparam state {
  BackgroundColor #E8F5E9
  BorderColor #2E7D32
  BackgroundColor<<Stub>> #FFF8E1
  BorderColor<<Stub>> #F9A825
  BackgroundColor<<Planned>> #ECEFF1
  BorderColor<<Planned>> #78909C
}

state "CAD-модель готова" as ModelReady
state "Процесс отсутствует" as NoProcess
state "Черновик процесса\nтребует валидации" as Draft
state "Валидация выполняется" as Validating
state "Validation failed\nсистемная ошибка" as Failed
state "Invalid\nесть ошибки" as Invalid
state "Valid with warnings" as ValidWarnings
state "Valid" as Valid
state "Результат валидации\nустарел" as Stale

state "Команда моделирования\nпрошла gate" as SimulationGate <<Stub>>
state "Моделирование\nвыполняется" as Simulating <<Planned>>
state "SimulationResult\nсохранён" as Simulated <<Planned>>
state "Отчёт сформирован" as ReportReady <<Planned>>
state "Отчёт экспортирован" as Exported <<Planned>>

[*] --> ModelReady : создать или импортировать solid
ModelReady --> NoProcess : активировать CHT Workbench
NoProcess --> Draft : «Создать процесс»

Draft --> Draft : добавить/удалить этап\nизменить параметры
Draft --> Validating : «Валидировать»
Invalid --> Draft : исправить процесс или модель
Failed --> Draft : устранить системную причину
Stale --> Validating : повторная валидация

Validating --> Failed : документ/модель/rules недоступны\nили анализ/сохранение завершились с ошибкой
Validating --> Invalid : есть ERROR
Validating --> ValidWarnings : нет ERROR, есть WARNING
Validating --> Valid : нет ERROR и WARNING

Invalid --> Validating : повторить проверку
Failed --> Validating : повторить проверку

Valid --> Stale : изменить модель, процесс,\nэтапы или rules.yaml
ValidWarnings --> Stale : изменить модель, процесс,\nэтапы или rules.yaml
Stale --> Draft : продолжить редактирование

Valid --> SimulationGate : «Запустить моделирование»\nstatus + fingerprint совпадают
ValidWarnings --> SimulationGate : «Запустить моделирование»\nstatus + fingerprint совпадают
Invalid --> Invalid : моделирование заблокировано
Failed --> Failed : моделирование заблокировано
Stale --> Stale : моделирование заблокировано

SimulationGate -[#9E9E9E,dashed]-> Simulating : planned: передать входные данные
Simulating -[#9E9E9E,dashed]-> Simulated : расчёт и цветовая карта успешны
Simulating -[#9E9E9E,dashed]-> Valid : ошибка расчёта,\nсохранить предыдущую валидацию
Simulated -[#9E9E9E,dashed]-> ReportReady : «Отчёт»
ReportReady -[#9E9E9E,dashed]-> Exported : сохранить HTML/PDF/DOCX
Simulated --> Stale : изменить модель или процесс
ReportReady --> Stale : изменить модель или процесс

NoProcess --> NoProcess : «Добавить этап» фактически\nсоздаёт процесс автоматически

note right of Stale
  Отдельный persisted-флаг stale отсутствует.
  ValidationEngine.can_simulate() вычисляет
  текущий fingerprint и сравнивает его с
  CHTValidationResult.InputFingerprint.
end note

note right of SimulationGate
  Текущее конечное состояние команды:
  информационное сообщение о заглушке.
  Переход к Simulating ещё не реализован.
end note

note bottom of NoProcess
  Требования предписывают ошибку при добавлении
  этапа без процесса, но add_stage_to_process()
  вызывает ensure_process_group().
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

Статусы `VALID`, `VALID_WITH_WARNINGS`, `INVALID` и `VALIDATION_FAILED` соответствуют `ValidationStatus`. Устаревание является вычисляемым состоянием: оно обнаруживается перед моделированием по несовпадению fingerprint, а не сохраняется отдельным свойством документа.
