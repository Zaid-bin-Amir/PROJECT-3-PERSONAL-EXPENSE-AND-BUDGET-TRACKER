import csv
import json
import os
import tempfile
from pathlib import Path

from .validators import (
    ValidationError,
    validate_amount,
    validate_category,
    validate_date,
    validate_description,
    validate_month,
)

CSV_FIELDS = ("id", "date", "category", "amount", "description")
FORMULA_PREFIXES = ("=", "+", "-", "@")


class StorageError(Exception):
    pass


def default_data():
    return {"next_id": 1, "expenses": [], "budgets": {}}


def clean_record(record):
    if not isinstance(record, dict):
        return None
    expense_id = record.get("id")
    if not isinstance(expense_id, int) or isinstance(expense_id, bool) or expense_id < 1:
        return None
    try:
        return {
            "id": expense_id,
            "date": validate_date(record.get("date"), allow_future=True),
            "category": validate_category(record.get("category")),
            "amount": validate_amount(record.get("amount")),
            "description": validate_description(record.get("description", "")),
        }
    except ValidationError:
        return None


def normalize_data(raw):
    data = default_data()
    if not isinstance(raw, dict):
        return data
    seen_ids = set()
    records = raw.get("expenses", [])
    if isinstance(records, list):
        for record in records:
            cleaned = clean_record(record)
            if cleaned is None or cleaned["id"] in seen_ids:
                continue
            seen_ids.add(cleaned["id"])
            data["expenses"].append(cleaned)
    budgets = raw.get("budgets", {})
    if isinstance(budgets, dict):
        for month, amount in budgets.items():
            try:
                data["budgets"][validate_month(month)] = validate_amount(amount)
            except ValidationError:
                continue
    highest = max(seen_ids, default=0)
    next_id = raw.get("next_id", 1)
    if not isinstance(next_id, int) or isinstance(next_id, bool) or next_id <= highest:
        next_id = highest + 1
    data["next_id"] = next_id
    return data


class JsonStorage:
    def __init__(self, path):
        self.path = Path(path).expanduser()

    def load(self):
        if not self.path.exists():
            return default_data()
        try:
            if self.path.stat().st_size == 0:
                return default_data()
            with self.path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.backup_corrupt_file()
            return default_data()
        except OSError as error:
            raise StorageError(f"Could not read {self.path}: {error}") from error
        return normalize_data(raw)

    def backup_corrupt_file(self):
        backup = self.path.with_name(self.path.name + ".corrupt")
        try:
            os.replace(self.path, backup)
        except OSError as error:
            raise StorageError(f"Data file {self.path} is damaged and could not be backed up: {error}") from error

    def save(self, data):
        temp_name = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle, temp_name = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(data, stream, indent=2, ensure_ascii=False)
            os.replace(temp_name, self.path)
            temp_name = None
        except (OSError, TypeError, ValueError) as error:
            raise StorageError(f"Could not save data to {self.path}: {error}") from error
        finally:
            if temp_name and os.path.exists(temp_name):
                os.remove(temp_name)


def safe_cell(value):
    text = str(value)
    if text.startswith(FORMULA_PREFIXES):
        return "'" + text
    return text


def export_expenses_csv(path, expenses):
    target = Path(path).expanduser()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(CSV_FIELDS)
            for item in expenses:
                writer.writerow([safe_cell(item[field]) for field in CSV_FIELDS])
    except OSError as error:
        raise StorageError(f"Could not export to {target}: {error}") from error
    return str(target)
