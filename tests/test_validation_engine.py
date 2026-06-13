import copy
import unittest
from pathlib import Path

import FreeCAD
import Part
import yaml

import tree
from rule_engine.engine import ValidationEngine
from rule_engine.models import ValidationStatus
from rule_engine.rules import default_rules_path, load_rules


class ValidationEngineTests(unittest.TestCase):
    document_index = 0

    def setUp(self):
        type(self).document_index += 1
        self.document_name = "CHTValidationTest{0}".format(self.document_index)
        self.document = FreeCAD.newDocument(self.document_name)
        self.model = self.document.addObject("Part::Feature", "TestPart")
        self.model.Shape = Part.makeBox(40, 20, 8)
        self.process = tree.ensure_default_process_tree(self.document)
        self.process.TargetObject = self.model
        self.process.TargetPart = self.model.Label
        self.engine = ValidationEngine()

    def tearDown(self):
        if FreeCAD.getDocument(self.document_name) is not None:
            FreeCAD.closeDocument(self.document_name)

    def stage(self, stage_type):
        return next(
            stage
            for stage in self.process.Group
            if getattr(stage, "StageType", "") == stage_type
        )

    def validate(self):
        return self.engine.validate(self.document, [self.model])

    def temporary_rules(self, mutate):
        data = copy.deepcopy(load_rules().data)
        mutate(data)
        path = Path(__file__).parent / "_rules_{0}.yaml".format(
            type(self).document_index
        )
        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return path

    def test_default_process_is_usable_with_explainable_warnings(self):
        result = self.validate()

        self.assertEqual(ValidationStatus.VALID_WITH_WARNINGS, result.status)
        self.assertEqual(0, result.error_count)
        self.assertIn("HTO-GEO-002", [message.code for message in result.messages])
        self.assertTrue(result.fingerprint)

    def test_missing_required_stage_is_invalid(self):
        stage = self.stage("Quenching")
        self.document.removeObject(stage.Name)

        result = self.validate()

        self.assertEqual(ValidationStatus.INVALID, result.status)
        self.assertIn("HTO-PROC-001", [message.code for message in result.messages])

    def test_wrong_stage_order_is_invalid(self):
        cementation = self.stage("Cementation")
        quenching = self.stage("Quenching")
        cementation.SequenceNumber = 3
        quenching.SequenceNumber = 2

        result = self.validate()

        self.assertEqual(ValidationStatus.INVALID, result.status)
        self.assertIn("HTO-PROC-003", [message.code for message in result.messages])

    def test_stage_parameter_outside_range_is_invalid(self):
        self.stage("Cementation").Temperature = 1050.0

        result = self.validate()

        self.assertEqual(ValidationStatus.INVALID, result.status)
        self.assertIn("HTO-PARAM-002", [message.code for message in result.messages])

    def test_unknown_material_is_warning(self):
        self.process.Material = "ExperimentalSteel"

        result = self.validate()

        self.assertEqual(ValidationStatus.VALID_WITH_WARNINGS, result.status)
        self.assertIn("HTO-MAT-003", [message.code for message in result.messages])

    def test_selected_model_becomes_persistent_process_target(self):
        second_model = self.document.addObject("Part::Feature", "SecondPart")
        second_model.Shape = Part.makeBox(20, 20, 20)

        self.engine.validate(self.document, [second_model])

        self.assertEqual(second_model, self.process.TargetObject)
        self.assertEqual(second_model.Label, self.process.TargetPart)

    def test_incompatible_u8_material_is_invalid(self):
        self.process.Material = "У8"

        result = self.validate()

        self.assertEqual(ValidationStatus.INVALID, result.status)
        self.assertIn("HTO-MAT-004", [message.code for message in result.messages])

    def test_thin_plate_and_slender_geometry_are_reported(self):
        self.model.Shape = Part.makeBox(100, 100, 1)

        result = self.validate()
        codes = [message.code for message in result.messages]

        self.assertIn("HTO-GEO-001", codes)
        self.assertIn("HTO-GEO-006", codes)
        self.assertIn("HTO-GEO-008", codes)
        thin_wall = next(
            message for message in result.messages if message.code == "HTO-GEO-001"
        )
        self.assertTrue(thin_wall.subelements)

    def test_small_hole_is_reported_with_face_reference(self):
        self.model.Shape = Part.makeBox(40, 20, 8).cut(
            Part.makeCylinder(2, 8, FreeCAD.Vector(20, 10, 0))
        )

        result = self.validate()
        hole = next(
            message for message in result.messages if message.code == "HTO-GEO-003"
        )

        self.assertTrue(any(name.startswith("Face") for name in hole.subelements))

    def test_open_shell_causes_validation_failed(self):
        self.model.Shape = Part.makePlane(10, 10)

        result = self.validate()

        self.assertEqual(ValidationStatus.VALIDATION_FAILED, result.status)
        self.assertIn("HTO-MODEL-002", [message.code for message in result.messages])

    def test_strict_mode_promotes_warning_to_error(self):
        rules_path = self.temporary_rules(
            lambda data: data["validation"].update(strictness="strict")
        )

        result = ValidationEngine(rules_path).validate(
            self.document, [self.model]
        )

        self.assertEqual(ValidationStatus.INVALID, result.status)
        sharp_edge = next(
            message for message in result.messages if message.code == "HTO-GEO-002"
        )
        self.assertEqual("ERROR", sharp_edge.severity.value)

    def test_soft_mode_demotes_process_error_to_warning(self):
        self.stage("Cementation").Temperature = 1050.0
        rules_path = self.temporary_rules(
            lambda data: data["validation"].update(strictness="soft")
        )

        result = ValidationEngine(rules_path).validate(
            self.document, [self.model]
        )
        temperature = next(
            message for message in result.messages if message.code == "HTO-PARAM-002"
        )

        self.assertEqual(ValidationStatus.VALID_WITH_WARNINGS, result.status)
        self.assertEqual("WARNING", temperature.severity.value)

    def test_disabled_sharp_edge_rule_is_not_evaluated(self):
        rules_path = self.temporary_rules(
            lambda data: data["geometry_rules"]["check_sharp_edges"].update(
                enabled=False
            )
        )

        result = ValidationEngine(rules_path).validate(
            self.document, [self.model]
        )

        self.assertNotIn(
            "HTO-GEO-002", [message.code for message in result.messages]
        )
        self.assertEqual(ValidationStatus.VALID, result.status)

    def test_message_text_can_be_overridden_by_rule_code(self):
        def override_message(data):
            data["messages"]["HTO-GEO-002"] = {
                "problem": "Пользовательский текст о кромках.",
                "cause": "{cause}",
                "recommendation": "Пользовательская рекомендация.",
            }

        rules_path = self.temporary_rules(override_message)

        result = ValidationEngine(rules_path).validate(
            self.document, [self.model]
        )
        sharp_edge = next(
            message for message in result.messages if message.code == "HTO-GEO-002"
        )

        self.assertEqual("Пользовательский текст о кромках.", sharp_edge.problem)
        self.assertEqual(
            "Пользовательская рекомендация.", sharp_edge.recommendation
        )

    def test_malformed_rules_cause_validation_failed(self):
        path = Path(__file__).parent / "_malformed_rules.yaml"
        path.write_text("validation: [broken", encoding="utf-8")
        self.addCleanup(lambda: path.unlink(missing_ok=True))

        result = ValidationEngine(path).validate(self.document, [self.model])

        self.assertEqual(ValidationStatus.VALIDATION_FAILED, result.status)
        self.assertIn("HTO-SYS-002", [message.code for message in result.messages])

    def test_result_is_persisted_and_current_success_allows_simulation(self):
        result = self.validate()
        saved = self.document.getObject("CHTValidationResult")

        self.assertIsNotNone(saved)
        self.assertEqual(result.status.value, saved.ValidationStatus)
        self.assertEqual(result.fingerprint, saved.InputFingerprint)
        allowed, reason = self.engine.can_simulate(self.document, [self.model])
        self.assertTrue(allowed, reason)

    def test_changed_process_makes_successful_result_stale(self):
        self.validate()
        self.process.TargetCaseDepth = 1.2

        allowed, reason = self.engine.can_simulate(self.document, [self.model])

        self.assertFalse(allowed)
        self.assertIn("изменились", reason)

    def test_missing_result_blocks_simulation(self):
        allowed, reason = self.engine.can_simulate(self.document, [self.model])

        self.assertFalse(allowed)
        self.assertIn("сначала выполните валидацию", reason)

    def test_invalid_result_blocks_simulation(self):
        self.stage("Cementation").Temperature = 1050.0
        self.validate()

        allowed, reason = self.engine.can_simulate(self.document, [self.model])

        self.assertFalse(allowed)
        self.assertIn("INVALID", reason)

    def test_rules_file_has_expected_demo_materials(self):
        rules = load_rules(default_rules_path())

        self.assertIn("20Х", rules.data["materials"])
        self.assertIn("У8", rules.data["materials"])

    def test_missing_document_returns_validation_failed(self):
        result = self.engine.validate(None)

        self.assertEqual(ValidationStatus.VALIDATION_FAILED, result.status)
        self.assertIn("HTO-SYS-001", [message.code for message in result.messages])


if __name__ == "__main__":
    unittest.main()
