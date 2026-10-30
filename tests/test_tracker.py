import csv
import json
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import main as app_main
from expense_tracker.cli import ExpenseTrackerCLI
from expense_tracker.manager import ExpenseManager, NotFoundError
from expense_tracker.storage import JsonStorage, StorageError, default_data, export_expenses_csv
from expense_tracker.validators import (
    ValidationError,
    validate_amount,
    validate_category,
    validate_date,
    validate_description,
    validate_expense_id,
    validate_month,
)


class ScriptedIO:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.lines = []

    def read(self, prompt=""):
        try:
            return next(self.answers)
        except StopIteration:
            raise EOFError() from None

    def write(self, text=""):
        self.lines.append(str(text))

    @property
    def text(self):
        return "\n".join(self.lines)


class FailingStorage:
    def load(self):
        return default_data()

    def save(self, data):
        raise StorageError("disk is full")


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.data_file = self.tmp_path / "expenses.json"

    def new_manager(self):
        return ExpenseManager(JsonStorage(self.data_file))

    def seeded_manager(self):
        manager = self.new_manager()
        manager.add_expense(100, "food", "Lunch", "2024-03-10")
        manager.add_expense("250.50", "transport", "Taxi ride", "2024-03-10")
        manager.add_expense(1000, "bills", "Electricity", "2024-03-15")
        manager.add_expense(75, "food", "Snacks", "2024-04-02")
        return manager


class ValidatorTests(unittest.TestCase):
    def test_amount_accepts_valid_values(self):
        self.assertEqual(validate_amount("250"), 250.0)
        self.assertEqual(validate_amount("1,200.50"), 1200.5)
        self.assertEqual(validate_amount(10), 10.0)
        self.assertEqual(validate_amount(10_000_000), 10_000_000.0)
        self.assertEqual(validate_amount("19.999"), 20.0)

    def test_amount_rejects_invalid_values(self):
        for value in ["", "  ", "abc", "-5", "0", "0.001", "nan", "inf", "1e3", "12abc", True, None, 10_000_001, "9" * 400]:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    validate_amount(value)

    def test_date_accepts_and_normalizes(self):
        self.assertEqual(validate_date("2024-03-10"), "2024-03-10")
        self.assertEqual(validate_date("2024-3-5"), "2024-03-05")
        self.assertEqual(validate_date(date(2024, 1, 2)), "2024-01-02")

    def test_date_rejects_invalid_values(self):
        for value in ["", "2024-13-01", "2024-02-30", "05-03-2024", "yesterday", "1999-12-31", None, 20240310]:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    validate_date(value)

    def test_date_future_handling(self):
        tomorrow = date.today() + timedelta(days=1)
        with self.assertRaises(ValidationError):
            validate_date(tomorrow)
        self.assertEqual(validate_date(tomorrow, allow_future=True), tomorrow.strftime("%Y-%m-%d"))

    def test_month_validation(self):
        self.assertEqual(validate_month("2024-03"), "2024-03")
        self.assertEqual(validate_month("2024-3"), "2024-03")
        for value in ["", "2024-13", "March", "2024-03-01", None, 202403]:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    validate_month(value)

    def test_category_validation(self):
        self.assertEqual(validate_category("  food  "), "Food")
        self.assertEqual(validate_category("food   court"), "Food Court")
        self.assertEqual(validate_category("food & drinks"), "Food & Drinks")
        for value in ["", "   ", "123", "food!", "a" * 31, None, 5]:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    validate_category(value)

    def test_description_validation(self):
        self.assertEqual(validate_description(None), "")
        self.assertEqual(validate_description("  big   lunch "), "big lunch")
        with self.assertRaises(ValidationError):
            validate_description("x" * 101)
        with self.assertRaises(ValidationError):
            validate_description(5)

    def test_expense_id_validation(self):
        self.assertEqual(validate_expense_id("7"), 7)
        for value in ["", "abc", "0", "-1", "2.5", None, True]:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    validate_expense_id(value)


class StorageTests(TempDirCase):
    def test_missing_file_gives_default_data(self):
        self.assertEqual(JsonStorage(self.data_file).load(), default_data())

    def test_empty_file_gives_default_data(self):
        self.data_file.write_text("", encoding="utf-8")
        self.assertEqual(JsonStorage(self.data_file).load(), default_data())

    def test_save_and_load_round_trip(self):
        storage = JsonStorage(self.data_file)
        data = {
            "next_id": 2,
            "expenses": [
                {"id": 1, "date": "2024-03-10", "category": "Food", "amount": 99.5, "description": "Lunch"}
            ],
            "budgets": {"2024-03": 5000.0},
        }
        storage.save(data)
        self.assertEqual(storage.load(), data)

    def test_save_creates_missing_folder_and_leaves_no_temp_files(self):
        target = self.tmp_path / "nested" / "folder" / "expenses.json"
        JsonStorage(target).save(default_data())
        self.assertTrue(target.exists())
        self.assertEqual([item.name for item in target.parent.iterdir()], ["expenses.json"])

    def test_corrupt_file_is_backed_up(self):
        self.data_file.write_text("{not valid json", encoding="utf-8")
        data = JsonStorage(self.data_file).load()
        self.assertEqual(data, default_data())
        backup = self.data_file.with_name("expenses.json.corrupt")
        self.assertTrue(backup.exists())
        self.assertEqual(backup.read_text(encoding="utf-8"), "{not valid json")

    def test_invalid_records_are_skipped(self):
        raw = {
            "next_id": 1,
            "expenses": [
                {"id": 1, "date": "2024-03-10", "category": "Food", "amount": 50, "description": "ok"},
                {"id": 2, "date": "2024-03-11", "category": "Food", "amount": -5, "description": "bad amount"},
                {"id": 1, "date": "2024-03-12", "category": "Food", "amount": 10, "description": "duplicate id"},
                {"id": 3, "date": "not a date", "category": "Food", "amount": 10},
                "garbage",
                {"id": 5, "date": "2024-03-13", "category": "bills", "amount": "20"},
            ],
            "budgets": {"2024-03": 100, "bad": 50, "2024-04": -1},
        }
        self.data_file.write_text(json.dumps(raw), encoding="utf-8")
        data = JsonStorage(self.data_file).load()
        self.assertEqual([item["id"] for item in data["expenses"]], [1, 5])
        self.assertEqual(data["expenses"][1]["category"], "Bills")
        self.assertEqual(data["budgets"], {"2024-03": 100.0})
        self.assertEqual(data["next_id"], 6)

    def test_wrong_top_level_type_gives_default_data(self):
        self.data_file.write_text("[1, 2, 3]", encoding="utf-8")
        self.assertEqual(JsonStorage(self.data_file).load(), default_data())

    def test_csv_export_content_and_formula_protection(self):
        target = self.tmp_path / "out" / "export.csv"
        expenses = [
            {"id": 1, "date": "2024-03-10", "category": "Food", "amount": 10.5, "description": "Lunch, big"},
            {"id": 2, "date": "2024-03-11", "category": "Other", "amount": 5.0, "description": "=SUM(A1)"},
        ]
        export_expenses_csv(target, expenses)
        with target.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[0], ["id", "date", "category", "amount", "description"])
        self.assertEqual(rows[1], ["1", "2024-03-10", "Food", "10.5", "Lunch, big"])
        self.assertEqual(rows[2][4], "'=SUM(A1)")

    def test_csv_export_to_invalid_path_raises(self):
        with self.assertRaises(StorageError):
            export_expenses_csv(self.tmp_path, [])


class ManagerTests(TempDirCase):
    def test_add_expense_assigns_incrementing_ids_and_persists(self):
        manager = self.new_manager()
        first = manager.add_expense(100, "food", "Lunch", "2024-03-10")
        second = manager.add_expense("50", "Transport")
        self.assertEqual(first["id"], 1)
        self.assertEqual(second["id"], 2)
        self.assertEqual(second["date"], date.today().strftime("%Y-%m-%d"))
        reloaded = self.new_manager()
        self.assertEqual(len(reloaded.list_expenses()), 2)
        self.assertEqual(reloaded.get_expense(1)["description"], "Lunch")

    def test_blank_date_means_today(self):
        manager = self.new_manager()
        record = manager.add_expense(10, "food", "", "  ")
        self.assertEqual(record["date"], date.today().strftime("%Y-%m-%d"))

    def test_invalid_add_changes_nothing(self):
        manager = self.new_manager()
        bad_calls = [
            (-5, "food"),
            ("abc", "food"),
            (10, ""),
            (10, "123"),
        ]
        for amount, category in bad_calls:
            with self.assertRaises(ValidationError):
                manager.add_expense(amount, category)
        with self.assertRaises(ValidationError):
            manager.add_expense(10, "food", "x" * 200)
        with self.assertRaises(ValidationError):
            manager.add_expense(10, "food", "", "2999-01-01")
        self.assertEqual(manager.list_expenses(), [])
        self.assertFalse(self.data_file.exists())

    def test_edit_expense(self):
        manager = self.seeded_manager()
        updated = manager.edit_expense(1, amount="120", category="snacks", description="Late lunch")
        self.assertEqual(updated["amount"], 120.0)
        self.assertEqual(updated["category"], "Snacks")
        self.assertEqual(updated["description"], "Late lunch")
        self.assertEqual(updated["date"], "2024-03-10")
        self.assertEqual(self.new_manager().get_expense(1)["amount"], 120.0)

    def test_edit_can_clear_description_and_change_date(self):
        manager = self.seeded_manager()
        updated = manager.edit_expense(1, description="", date_value="2024-03-12")
        self.assertEqual(updated["description"], "")
        self.assertEqual(updated["date"], "2024-03-12")

    def test_edit_errors_leave_data_unchanged(self):
        manager = self.seeded_manager()
        with self.assertRaises(ValidationError):
            manager.edit_expense(1)
        with self.assertRaises(ValidationError):
            manager.edit_expense(1, amount="-1")
        with self.assertRaises(ValidationError):
            manager.edit_expense(1, date_value="bad")
        with self.assertRaises(NotFoundError):
            manager.edit_expense(99, amount=5)
        with self.assertRaises(ValidationError):
            manager.edit_expense("x", amount=5)
        self.assertEqual(manager.get_expense(1)["amount"], 100.0)

    def test_delete_expense(self):
        manager = self.seeded_manager()
        removed = manager.delete_expense(2)
        self.assertEqual(removed["description"], "Taxi ride")
        self.assertEqual(len(manager.list_expenses()), 3)
        with self.assertRaises(NotFoundError):
            manager.get_expense(2)
        with self.assertRaises(NotFoundError):
            manager.delete_expense(2)

    def test_ids_are_not_reused_after_delete(self):
        manager = self.seeded_manager()
        manager.delete_expense(4)
        record = manager.add_expense(5, "food", "", "2024-05-01")
        self.assertEqual(record["id"], 5)
        reloaded = self.new_manager()
        self.assertEqual(reloaded.add_expense(5, "food", "", "2024-05-02")["id"], 6)

    def test_list_sorting(self):
        manager = self.seeded_manager()
        by_date = manager.list_expenses()
        self.assertEqual([item["id"] for item in by_date], [1, 2, 3, 4])
        by_amount = manager.list_expenses("amount", True)
        self.assertEqual(by_amount[0]["amount"], 1000.0)
        self.assertEqual(by_amount[-1]["amount"], 75.0)
        by_category = manager.list_expenses("category")
        self.assertEqual(by_category[0]["category"], "Bills")
        with self.assertRaises(ValidationError):
            manager.list_expenses("colour")

    def test_returned_records_are_copies(self):
        manager = self.seeded_manager()
        manager.get_expense(1)["amount"] = 999999
        manager.list_expenses()[0]["amount"] = 999999
        self.assertEqual(manager.get_expense(1)["amount"], 100.0)

    def test_search_filters(self):
        manager = self.seeded_manager()
        self.assertEqual(len(manager.search_expenses()), 4)
        self.assertEqual(len(manager.search_expenses(keyword="  ")), 4)
        self.assertEqual([i["id"] for i in manager.search_expenses(keyword="TAXI")], [2])
        self.assertEqual(len(manager.search_expenses(keyword="food")), 2)
        self.assertEqual(len(manager.search_expenses(category="FOOD")), 2)
        self.assertEqual(len(manager.search_expenses(start_date="2024-03-01", end_date="2024-03-31")), 3)
        self.assertEqual(len(manager.search_expenses(start_date="2024-03-11")), 2)
        self.assertEqual(len(manager.search_expenses(min_amount=200)), 2)
        self.assertEqual(len(manager.search_expenses(max_amount=100)), 2)
        self.assertEqual(
            [i["id"] for i in manager.search_expenses(category="food", min_amount=80, end_date="2024-03-31")],
            [1],
        )
        self.assertEqual(manager.search_expenses(keyword="nothing matches this"), [])

    def test_search_rejects_bad_ranges(self):
        manager = self.seeded_manager()
        with self.assertRaises(ValidationError):
            manager.search_expenses(start_date="2024-04-01", end_date="2024-03-01")
        with self.assertRaises(ValidationError):
            manager.search_expenses(min_amount=500, max_amount=100)
        with self.assertRaises(ValidationError):
            manager.search_expenses(category="123")

    def test_totals(self):
        manager = self.seeded_manager()
        self.assertEqual(manager.daily_total("2024-03-10"), 350.5)
        self.assertEqual(manager.daily_total("2024-03-11"), 0.0)
        self.assertEqual(manager.monthly_total("2024-03"), 1350.5)
        self.assertEqual(manager.monthly_total("2024-04"), 75.0)
        self.assertEqual(manager.monthly_total("2023-01"), 0.0)
        self.assertEqual(
            manager.category_totals(),
            {"Bills": 1000.0, "Transport": 250.5, "Food": 175.0},
        )
        self.assertEqual(
            manager.category_totals("2024-03"),
            {"Bills": 1000.0, "Transport": 250.5, "Food": 100.0},
        )
        self.assertEqual(
            manager.daily_totals("2024-03"),
            {"2024-03-10": 350.5, "2024-03-15": 1000.0},
        )

    def test_totals_default_to_today_and_current_month(self):
        manager = self.new_manager()
        manager.add_expense(40, "food")
        manager.add_expense(60, "food")
        self.assertEqual(manager.daily_total(), 100.0)
        self.assertEqual(manager.monthly_total(), 100.0)
        with self.assertRaises(ValidationError):
            manager.daily_total("nope")
        with self.assertRaises(ValidationError):
            manager.monthly_total("2024-13")

    def test_float_totals_do_not_drift(self):
        manager = self.new_manager()
        for _ in range(10):
            manager.add_expense("0.1", "food", "", "2024-03-10")
        self.assertEqual(manager.daily_total("2024-03-10"), 1.0)

    def test_summary(self):
        manager = self.seeded_manager()
        summary = manager.spending_summary("2024-03")
        self.assertEqual(summary["total"], 1350.5)
        self.assertEqual(summary["count"], 3)
        self.assertEqual(summary["average"], 450.17)
        self.assertEqual(summary["highest_expense"]["description"], "Electricity")
        self.assertEqual(summary["categories"][0]["category"], "Bills")
        self.assertAlmostEqual(sum(entry["percent"] for entry in summary["categories"]), 100.0, delta=0.2)
        self.assertEqual(summary["budget"]["state"], "no_budget")

    def test_summary_for_empty_month(self):
        summary = self.seeded_manager().spending_summary("2020-01")
        self.assertEqual(summary["total"], 0.0)
        self.assertEqual(summary["count"], 0)
        self.assertEqual(summary["average"], 0.0)
        self.assertIsNone(summary["highest_expense"])
        self.assertEqual(summary["categories"], [])

    def test_budget_states(self):
        manager = self.seeded_manager()
        self.assertEqual(manager.budget_status("2024-04")["state"], "no_budget")
        self.assertIsNone(manager.get_budget("2024-03"))

        manager.set_budget("2024-03", 2000)
        status = manager.budget_status("2024-03")
        self.assertEqual(status["state"], "ok")
        self.assertEqual(status["remaining"], 649.5)
        self.assertEqual(status["percent_used"], 67.5)

        manager.set_budget("2024-03", 1500)
        self.assertEqual(manager.budget_status("2024-03")["state"], "warning")

        manager.set_budget("2024-03", 1350.5)
        status = manager.budget_status("2024-03")
        self.assertEqual(status["state"], "warning")
        self.assertEqual(status["remaining"], 0.0)

        manager.set_budget("2024-03", 1000)
        status = manager.budget_status("2024-03")
        self.assertEqual(status["state"], "over")
        self.assertEqual(status["remaining"], -350.5)
        self.assertEqual(manager.get_budget("2024-03"), 1000.0)

    def test_budget_persists_and_validates(self):
        manager = self.new_manager()
        manager.set_budget("2024-3", "5,000")
        self.assertEqual(self.new_manager().get_budget("2024-03"), 5000.0)
        with self.assertRaises(ValidationError):
            manager.set_budget("2024-03", 0)
        with self.assertRaises(ValidationError):
            manager.set_budget("March", 100)
        with self.assertRaises(ValidationError):
            manager.set_budget(None, 100)

    def test_failed_save_rolls_back_in_memory_state(self):
        manager = ExpenseManager(FailingStorage())
        with self.assertRaises(StorageError):
            manager.add_expense(10, "food")
        with self.assertRaises(StorageError):
            manager.set_budget("2024-03", 100)
        self.assertEqual(manager.list_expenses(), [])
        self.assertIsNone(manager.get_budget("2024-03"))

    def test_export_to_csv(self):
        manager = self.seeded_manager()
        target = self.tmp_path / "export.csv"
        manager.export_to_csv(target)
        with target.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["description"], "Lunch")


class CLITests(TempDirCase):
    def run_cli(self, answers, manager=None):
        manager = manager or self.new_manager()
        io = ScriptedIO(answers)
        cli = ExpenseTrackerCLI(
            manager,
            input_func=io.read,
            output_func=io.write,
            default_export_path=self.tmp_path / "default_export.csv",
        )
        cli.run()
        return manager, io

    def test_exit(self):
        _, io = self.run_cli(["0"])
        self.assertIn("Goodbye!", io.text)

    def test_invalid_menu_option(self):
        _, io = self.run_cli(["99", "abc", "", "0"])
        self.assertEqual(io.text.count("Invalid option"), 3)

    def test_add_expense(self):
        manager, io = self.run_cli(["1", "100", "food", "Lunch", "2024-03-10", "0"])
        self.assertEqual(len(manager.list_expenses()), 1)
        self.assertIn("Expense #1 added", io.text)

    def test_add_expense_retries_until_valid(self):
        manager, io = self.run_cli(["1", "abc", "-5", "100", "123", "food", "", "2999-01-01", "", "0"])
        records = manager.list_expenses()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["amount"], 100.0)
        self.assertEqual(records[0]["category"], "Food")
        self.assertEqual(records[0]["date"], date.today().strftime("%Y-%m-%d"))
        self.assertEqual(io.text.count("Invalid input"), 4)

    def test_cancel_returns_to_menu(self):
        manager, io = self.run_cli(["1", "50", "cancel", "0"])
        self.assertEqual(manager.list_expenses(), [])
        self.assertIn("Cancelled.", io.text)

    def test_add_warns_when_over_budget(self):
        manager = self.new_manager()
        manager.set_budget("2024-03", 100)
        _, io = self.run_cli(["1", "150", "food", "", "2024-03-10", "0"], manager)
        self.assertIn("Alert: you are over your budget for 2024-03", io.text)

    def test_view_expenses_sorted(self):
        _, io = self.run_cli(["2", "amount", "y", "0"], self.seeded_manager())
        self.assertLess(io.text.index("Electricity"), io.text.index("Snacks"))
        self.assertIn("4 expense(s)", io.text)

    def test_view_with_no_expenses(self):
        _, io = self.run_cli(["2", "", "", "0"])
        self.assertIn("No expenses found.", io.text)

    def test_edit_expense(self):
        manager, io = self.run_cli(["3", "1", "200", "", "-", "", "0"], self.seeded_manager())
        record = manager.get_expense(1)
        self.assertEqual(record["amount"], 200.0)
        self.assertEqual(record["description"], "")
        self.assertIn("Expense updated", io.text)

    def test_edit_with_no_changes_shows_error(self):
        _, io = self.run_cli(["3", "1", "", "", "", "", "0"], self.seeded_manager())
        self.assertIn("Error: Nothing to update", io.text)

    def test_edit_missing_expense(self):
        _, io = self.run_cli(["3", "99", "0"], self.seeded_manager())
        self.assertIn("Error: No expense found with ID 99.", io.text)

    def test_delete_requires_confirmation(self):
        manager, io = self.run_cli(["4", "1", "n", "0"], self.seeded_manager())
        self.assertEqual(len(manager.list_expenses()), 4)
        self.assertIn("Deletion cancelled.", io.text)
        manager, io = self.run_cli(["4", "1", "maybe", "y", "0"], manager)
        self.assertEqual(len(manager.list_expenses()), 3)
        self.assertIn("Please answer y or n.", io.text)
        self.assertIn("Expense #1 deleted.", io.text)

    def test_delete_missing_expense(self):
        manager, io = self.run_cli(["4", "99", "0"], self.seeded_manager())
        self.assertIn("Error: No expense found with ID 99.", io.text)
        self.assertEqual(len(manager.list_expenses()), 4)

    def test_search(self):
        _, io = self.run_cli(["5", "taxi", "", "", "", "", "", "0"], self.seeded_manager())
        self.assertIn("Taxi ride", io.text)
        self.assertNotIn("Lunch", io.text)

    def test_search_with_bad_range_shows_error(self):
        _, io = self.run_cli(["5", "", "", "2024-04-01", "2024-03-01", "", "", "0"], self.seeded_manager())
        self.assertIn("Error: Start date cannot be after end date.", io.text)

    def test_daily_total(self):
        _, io = self.run_cli(["6", "2024-03-10", "0"], self.seeded_manager())
        self.assertIn("Total spent on 2024-03-10: Rs 350.50", io.text)
        self.assertIn("Taxi ride", io.text)

    def test_monthly_summary(self):
        _, io = self.run_cli(["7", "2024-03", "0"], self.seeded_manager())
        self.assertIn("Spending summary for 2024-03", io.text)
        self.assertIn("Bills", io.text)
        self.assertIn("Rs 1,350.50", io.text)

    def test_budget_flow(self):
        manager, io = self.run_cli(["8", "2024-03", "1000", "9", "2024-03", "0"], self.seeded_manager())
        self.assertEqual(manager.get_budget("2024-03"), 1000.0)
        self.assertIn("Alert: you have exceeded your budget.", io.text)

    def test_budget_status_without_budget(self):
        _, io = self.run_cli(["9", "2024-03", "0"], self.seeded_manager())
        self.assertIn("No budget set for 2024-03", io.text)

    def test_export_csv(self):
        target = self.tmp_path / "exports" / "mine.csv"
        _, io = self.run_cli(["10", str(target), "0"], self.seeded_manager())
        self.assertTrue(target.exists())
        self.assertIn("Exported 4 expense(s)", io.text)

    def test_export_csv_default_path(self):
        self.run_cli(["10", "", "0"], self.seeded_manager())
        self.assertTrue((self.tmp_path / "default_export.csv").exists())

    def test_export_to_bad_path_shows_error(self):
        _, io = self.run_cli(["10", str(self.tmp_path), "0"], self.seeded_manager())
        self.assertIn("Error: Could not export", io.text)

    def test_end_of_input_raises_eof(self):
        with self.assertRaises(EOFError):
            self.run_cli(["1", "100"])


class MainTests(TempDirCase):
    def test_data_dir_defaults_next_to_main(self):
        with mock.patch.dict(os.environ, clear=False):
            os.environ.pop(app_main.DATA_DIR_ENV, None)
            self.assertEqual(app_main.resolve_data_dir().name, "data")

    def test_data_dir_can_be_overridden(self):
        with mock.patch.dict(os.environ, {app_main.DATA_DIR_ENV: str(self.tmp_path)}):
            self.assertEqual(app_main.resolve_data_dir(), self.tmp_path)

    def test_main_runs_and_saves(self):
        answers = iter(["1", "100", "food", "Lunch", "2024-03-10", "0"])
        with mock.patch.dict(os.environ, {app_main.DATA_DIR_ENV: str(self.tmp_path)}):
            with mock.patch("builtins.input", lambda prompt="": next(answers)):
                with mock.patch("builtins.print"):
                    self.assertEqual(app_main.main(), 0)
        saved = json.loads((self.tmp_path / "expenses.json").read_text(encoding="utf-8"))
        self.assertEqual(len(saved["expenses"]), 1)

    def test_main_exits_cleanly_on_end_of_input(self):
        def raise_eof(prompt=""):
            raise EOFError()

        with mock.patch.dict(os.environ, {app_main.DATA_DIR_ENV: str(self.tmp_path)}):
            with mock.patch("builtins.input", raise_eof):
                with mock.patch("builtins.print"):
                    self.assertEqual(app_main.main(), 0)

    def test_main_reports_unreadable_data_file(self):
        self.data_file.mkdir()
        with mock.patch.dict(os.environ, {app_main.DATA_DIR_ENV: str(self.tmp_path)}):
            with mock.patch("builtins.print") as fake_print:
                self.assertEqual(app_main.main(), 1)
        self.assertTrue(fake_print.called)


if __name__ == "__main__":
    unittest.main()
