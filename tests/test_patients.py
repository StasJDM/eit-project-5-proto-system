import os
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDateEdit, QDoubleSpinBox, QMessageBox

from app.application import (
    DIAGNOSIS_CLASSIFICATION_SETTING,
    DiagnosisCatalogService,
    DuplicatePatientError,
    EventBus,
    EventType,
    PatientDraft,
    PatientService,
    PatientValidationError,
    full_years,
    search_diagnoses,
    search_icd11,
)
from app.config import DataMode
from app.domain import Diagnosis, VentilationDetails, deserialize_model, serialize_model
from app.i18n import i18n
from app.screens.patient_screen import PatientScreen
from app.screens.eit_settings_screen import EITSettingsScreen
from app.storage import Database, RepositoryBundle


def valid_draft(**overrides):
    values = {
        "external_id": "P-00000001",
        "medical_record_number": "MR-0001",
        "family_name": "Иванов",
        "given_name": "Иван",
        "middle_name": "Иванович",
        "date_of_birth": date(1988, 10, 26),
        "sex": "male",
        "weight_kg": 78.5,
        "height_cm": 181.0,
        "chest_circumference_cm": 98.0,
    }
    values.update(overrides)
    return PatientDraft(**values)


class PatientServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name) / "patients.sqlite3"
        self.database = Database(self.path, DataMode.SIMULATION)
        self.repositories = RepositoryBundle.build(self.database)
        self.service = PatientService(self.repositories.patients)

    def tearDown(self):
        self.database.close()
        self.temp.cleanup()

    def test_task_7_patient_is_validated_saved_edited_and_reopened(self):
        patient = self.service.save(valid_draft())
        patient_id = patient.id
        created_at = patient.created_at_utc

        updated = self.service.save(
            valid_draft(weight_kg=80.0), patient_id=patient_id
        )
        self.assertEqual(updated.id, patient_id)
        self.assertEqual(updated.created_at_utc, created_at)
        self.assertEqual(updated.weight_kg, 80.0)

        self.database.close()
        self.database = Database(self.path, DataMode.SIMULATION)
        self.repositories = RepositoryBundle.build(self.database)
        self.service = PatientService(self.repositories.patients)
        self.assertEqual(self.repositories.patients.get(patient_id), updated)

        with self.assertRaises(PatientValidationError):
            self.service.save(valid_draft(weight_kg=0.1, external_id="P-00000002",
                                          medical_record_number="MR-0002"))

    def test_task_7_full_years_handles_birthday_boundary(self):
        born = date(2000, 10, 26)
        self.assertEqual(full_years(born, date(2026, 10, 25)), 25)
        self.assertEqual(full_years(born, date(2026, 10, 26)), 26)

    def test_task_8_generated_and_manual_ids_are_unique(self):
        generated = self.service.assign_external_id()
        first = self.service.save(valid_draft(external_id=generated))
        self.assertEqual(first.external_id, generated)
        self.assertNotEqual(self.service.assign_external_id(), generated)

        with self.assertRaises(DuplicatePatientError):
            self.service.save(valid_draft(
                external_id=generated.lower(), medical_record_number="MR-0002"
            ))
        with self.assertRaises(DuplicatePatientError):
            self.service.save(valid_draft(
                external_id="P-00000002", medical_record_number="MR-0001"
            ))

    def test_task_9_clinical_data_round_trips_without_loss(self):
        main = search_icd11("CB00")[0]
        accompanying = search_icd11("hypertension")[0]
        ventilation = VentilationDetails(
            enabled=True, mode="PCV", fio2_percent=45.0, peep_cmh2o=8.0
        )
        patient = self.service.save(valid_draft(
            main_diagnosis=main,
            accompanying_diagnoses=(accompanying,),
            ventilation=ventilation,
        ))
        loaded = self.repositories.patients.get(patient.id)
        self.assertEqual(loaded.main_diagnosis, main)
        self.assertEqual(loaded.accompanying_diagnoses, (accompanying,))
        self.assertEqual(loaded.ventilation, ventilation)

        with self.assertRaises(PatientValidationError):
            self.service.save(valid_draft(
                external_id="P-00000002",
                medical_record_number="MR-0002",
                ventilation=VentilationDetails(enabled=True),
            ))

    def test_task_9_catalogue_uses_verified_icd_11_codes(self):
        expected = {
            "Chronic obstructive pulmonary disease": "CA22",
            "Asthma": "CA23",
            "Acute respiratory distress syndrome": "CB00",
            "Respiratory failure": "CB41",
            "Pleural effusion": "CB27",
            "Pneumothorax": "CB21",
            "Acute myocardial infarction": "BA41",
        }
        for title, code in expected.items():
            with self.subTest(title=title):
                diagnosis = search_icd11(title)[0]
                self.assertEqual(diagnosis.code, code)
                self.assertEqual(diagnosis.title, title)

    def test_full_catalogues_search_russian_and_english_titles(self):
        self.assertGreater(len(search_diagnoses("", "ICD-10", limit=20_000)), 14_000)
        self.assertGreater(len(search_diagnoses("", "ICD-11", limit=40_000)), 35_000)

        icd10_ru = next(
            item for item in search_diagnoses("пневмония неуточненная", "ICD-10")
            if item.code == "J18.9"
        )
        icd10_en = next(
            item for item in search_diagnoses("pneumonia, unspecified", "ICD-10")
            if item.code == "J18.9"
        )
        self.assertEqual(icd10_ru.code, "J18.9")
        self.assertEqual(icd10_en.code, "J18.9")
        self.assertEqual(icd10_ru.title_ru, "Пневмония неуточненная")

        icd11_ru = search_diagnoses("холера", "ICD-11")[0]
        icd11_en = search_diagnoses("cholera", "ICD-11")[0]
        self.assertEqual(icd11_ru.code, "1A00")
        self.assertEqual(icd11_en.code, "1A00")
        self.assertEqual(icd11_ru.title_ru, "Холера")

    def test_icd_10_is_default_and_catalogue_choice_persists(self):
        event_bus = EventBus()
        events = []
        event_bus.subscribe(EventType.SETTINGS_CHANGED, events.append)
        catalogue = DiagnosisCatalogService(self.repositories.settings, event_bus)

        self.assertEqual(catalogue.classification, "ICD-10")
        self.assertEqual(search_diagnoses("J44.9")[0].classification, "ICD-10")
        catalogue.set_classification("ICD-11")

        self.assertEqual(
            self.repositories.settings.load()[DIAGNOSIS_CLASSIFICATION_SETTING],
            "ICD-11",
        )
        self.assertEqual(
            DiagnosisCatalogService(self.repositories.settings, EventBus()).classification,
            "ICD-11",
        )
        self.assertEqual(events[-1].payload[DIAGNOSIS_CLASSIFICATION_SETTING], "ICD-11")

    def test_diagnosis_classification_round_trips_with_patient(self):
        diagnosis = search_diagnoses("J18.9", "ICD-10")[0]
        patient = self.service.save(valid_draft(main_diagnosis=diagnosis))
        self.assertEqual(
            self.repositories.patients.get(patient.id).main_diagnosis.classification,
            "ICD-10",
        )

    def test_old_patient_payload_diagnosis_is_read_as_icd_11(self):
        diagnosis = search_icd11("CB00")[0]
        patient = self.service.save(valid_draft(main_diagnosis=diagnosis))
        payload = serialize_model(patient)
        payload["main_diagnosis"].pop("classification")

        restored = deserialize_model(payload)

        self.assertEqual(restored.main_diagnosis.classification, "ICD-11")

    def test_task_10_partial_search_is_bounded_and_empty_state_is_safe(self):
        self.assertEqual(self.service.search("unknown"), ())
        first = self.service.save(valid_draft())
        second = self.service.save(valid_draft(
            external_id="P-00000002", medical_record_number="MR-0002",
            family_name="Петров", given_name="Пётр",
        ))
        self.assertEqual(self.service.search("иванов иван"), (first,))
        self.assertEqual(self.service.search("0002"), (second,))
        self.assertEqual(len(self.service.search("", limit=1)), 1)

    def test_schema_v2_search_data_is_backfilled_by_migration(self):
        legacy_path = Path(self.temp.name) / "legacy.sqlite3"
        legacy = Database(legacy_path, DataMode.SIMULATION, target_version=2)
        legacy_repositories = RepositoryBundle.build(legacy)
        legacy_repositories.patients.save(valid_patient := self.service.save(valid_draft(
            external_id="P-LEGACY1", medical_record_number="LEGACY-1",
            family_name="Сидоров",
        )))
        legacy.close()

        migrated = Database(legacy_path, DataMode.SIMULATION)
        try:
            repository = RepositoryBundle.build(migrated).patients
            self.assertEqual(repository.search("сидор"), (valid_patient,))
        finally:
            migrated.close()


class PatientScreenContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_task_7_uses_typed_controls_without_changing_field_roles(self):
        screen = PatientScreen()
        try:
            self.assertIsInstance(screen._e_dob, QDateEdit)
            self.assertIsInstance(screen._e_weight, QDoubleSpinBox)
            self.assertIsInstance(screen._e_height, QDoubleSpinBox)
            self.assertIsInstance(screen._e_chest, QDoubleSpinBox)
            self.assertFalse(screen.has_unsaved_changes)
        finally:
            screen.close()

    def test_patient_diagnosis_title_follows_interface_language(self):
        screen = PatientScreen()
        previous_language = i18n.lang
        diagnosis = search_diagnoses("J18.9", "ICD-10")[0]
        try:
            screen._main_diagnosis = diagnosis
            i18n.set_language("ru")
            screen.retranslate()
            self.assertEqual(screen._e_main_diag.text(), "J18.9 — Пневмония неуточненная")

            i18n.set_language("en")
            screen.retranslate()
            self.assertEqual(screen._e_main_diag.text(), "J18.9 — Pneumonia, unspecified")
        finally:
            i18n.set_language(previous_language)
            screen.close()

    def test_task_7_marks_required_patient_fields_with_red_asterisks(self):
        screen = PatientScreen()
        try:
            required_rows = (
                screen._fr_last,
                screen._fr_first,
                screen._fr_dob,
                screen._fr_gender,
                screen._fr_record,
                screen._fr_weight,
                screen._fr_height,
                screen._fr_chest,
                screen._fr_id,
            )
            optional_rows = (
                screen._fr_patr,
                screen._fr_age,
            )

            self.assertTrue(all(row.required for row in required_rows))
            self.assertTrue(all("*" in row._lbl.text() for row in required_rows))
            self.assertTrue(all("#d32f2f" in row._lbl.text() for row in required_rows))
            self.assertTrue(all(not row.required for row in optional_rows))
            self.assertTrue(all("*" not in row._lbl.text() for row in optional_rows))
        finally:
            screen.close()

    def test_task_7_highlights_invalid_fields_and_clears_them_on_edit(self):
        with TemporaryDirectory() as directory:
            database = Database(Path(directory) / "validation.sqlite3", DataMode.SIMULATION)
            service = PatientService(RepositoryBundle.build(database).patients)
            screen = PatientScreen(patient_service=service)
            try:
                with patch("app.screens.patient_screen.QMessageBox.warning"):
                    screen._save()

                for field in (
                    screen._e_last,
                    screen._e_first,
                    screen._e_record,
                    screen._e_id,
                    screen._e_weight,
                    screen._e_height,
                    screen._e_chest,
                ):
                    self.assertTrue(field.property("validationError"))
                    self.assertTrue(field.toolTip())
                    self.assertNotIn("Value must", field.toolTip())
                self.assertFalse(screen._e_dob.property("validationError"))
                self.assertFalse(screen._cmb_gender.property("validationError"))
                self.assertEqual(
                    screen._e_weight.toolTip(), "Введите массу от 0,5 до 500 кг."
                )

                screen._e_last.setText("Иванов")
                self.assertFalse(screen._e_last.property("validationError"))
                self.assertEqual(screen._e_last.toolTip(), "")
            finally:
                screen.close()
                database.close()

    def test_task_7_localizes_unsaved_changes_dialog_buttons(self):
        screen = PatientScreen()
        previous_language = i18n.lang
        expected = {
            "ru": ("Не сохранять", "Отмена"),
            "en": ("Don't save", "Cancel"),
            "zh": ("不保存", "取消"),
            "vi": ("Không lưu", "Hủy"),
        }
        try:
            for language, labels in expected.items():
                with self.subTest(language=language):
                    i18n.set_language(language)
                    dialog = screen._create_unsaved_changes_dialog()
                    try:
                        self.assertEqual(
                            dialog.button(QMessageBox.Discard).text(), labels[0]
                        )
                        self.assertEqual(
                            dialog.button(QMessageBox.Cancel).text(), labels[1]
                        )
                    finally:
                        dialog.close()
        finally:
            i18n.set_language(previous_language)
            screen.close()

    def test_task_7_localizes_validation_tooltips_and_system_conclusions(self):
        screen = PatientScreen()
        previous_language = i18n.lang
        expected = {
            "ru": (
                "Введите массу от 0,5 до 500 кг.",
                "Завершено при закрытии приложения",
            ),
            "en": (
                "Enter a weight from 0.5 to 500 kg.",
                "Completed when the application was closed",
            ),
            "zh": ("请输入 0.5 至 500 千克的体重。", "应用关闭时结束"),
            "vi": (
                "Nhập cân nặng từ 0,5 đến 500 kg.",
                "Hoàn tất khi đóng ứng dụng",
            ),
        }
        try:
            for language, labels in expected.items():
                with self.subTest(language=language):
                    i18n.set_language(language)
                    self.assertEqual(
                        screen._localized_validation_message(
                            "weight_kg", "Value must be between 0.5 and 500"
                        ),
                        labels[0],
                    )
                    self.assertEqual(
                        screen._conclusion_text("application_closed"), labels[1]
                    )
        finally:
            i18n.set_language(previous_language)
            screen.close()

    def test_settings_screen_switches_catalogue_and_patient_placeholder(self):
        with TemporaryDirectory() as directory:
            database = Database(Path(directory) / "ui.sqlite3", DataMode.SIMULATION)
            repositories = RepositoryBundle.build(database)
            catalogue = DiagnosisCatalogService(repositories.settings, EventBus())
            settings_screen = EITSettingsScreen(catalogue)
            patient_screen = PatientScreen(diagnosis_catalog=catalogue)
            try:
                self.assertEqual(settings_screen._grp_diagnosis_catalog._state, "a")
                self.assertEqual(patient_screen._e_main_diag.placeholderText(), "МКБ-10")
                settings_screen._grp_diagnosis_catalog._select("b")
                settings_screen._save()
                patient_screen.refresh_diagnosis_catalog()
                self.assertEqual(catalogue.classification, "ICD-11")
                self.assertEqual(patient_screen._e_main_diag.placeholderText(), "МКБ-11")
            finally:
                settings_screen.close()
                patient_screen.close()
                database.close()


if __name__ == "__main__":
    unittest.main()
