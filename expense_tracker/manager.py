import copy
from datetime import date

from .storage import export_expenses_csv
from .validators import (
    DATE_FORMAT,
    MONTH_FORMAT,
    SORT_FIELDS,
    ValidationError,
    validate_amount,
    validate_category,
    validate_date,
    validate_description,
    validate_expense_id,
    validate_month,
)

WARNING_RATIO = 0.8

SORT_KEYS = {
    "date": lambda item: (item["date"], item["id"]),
    "amount": lambda item: (item["amount"], item["id"]),
    "category": lambda item: (item["category"].lower(), item["date"], item["id"]),
    "id": lambda item: item["id"],
}


class NotFoundError(LookupError):
    pass


def current_date():
    return date.today().strftime(DATE_FORMAT)


def current_month():
    return date.today().strftime(MONTH_FORMAT)


def is_blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def total_of(expenses):
    return round(sum(item["amount"] for item in expenses), 2)


class ExpenseManager:
    def __init__(self, storage):
        self.storage = storage
        self._data = storage.load()

    def _commit(self, data):
        self.storage.save(data)
        self._data = data

    def _locate(self, data, expense_id):
        number = validate_expense_id(expense_id)
        for index, item in enumerate(data["expenses"]):
            if item["id"] == number:
                return index
        raise NotFoundError(f"No expense found with ID {number}.")

    @staticmethod
    def _resolve_date(value, allow_future=False):
        if is_blank(value):
            return current_date()
        return validate_date(value, allow_future=allow_future)

    @staticmethod
    def _resolve_month(value):
        if is_blank(value):
            return current_month()
        return validate_month(value)

    def _month_items(self, month):
        prefix = month + "-"
        return [item for item in self._data["expenses"] if item["date"].startswith(prefix)]

    def add_expense(self, amount, category, description="", date_value=None):
        clean_amount = validate_amount(amount)
        clean_category = validate_category(category)
        clean_description = validate_description(description)
        clean_date = self._resolve_date(date_value)
        data = copy.deepcopy(self._data)
        record = {
            "id": data["next_id"],
            "date": clean_date,
            "category": clean_category,
            "amount": clean_amount,
            "description": clean_description,
        }
        data["next_id"] += 1
        data["expenses"].append(record)
        self._commit(data)
        return dict(record)

    def get_expense(self, expense_id):
        index = self._locate(self._data, expense_id)
        return dict(self._data["expenses"][index])

    def edit_expense(self, expense_id, amount=None, category=None, description=None, date_value=None):
        changes = {}
        if amount is not None:
            changes["amount"] = validate_amount(amount)
        if category is not None:
            changes["category"] = validate_category(category)
        if description is not None:
            changes["description"] = validate_description(description)
        if date_value is not None:
            changes["date"] = validate_date(date_value)
        if not changes:
            raise ValidationError("Nothing to update. Provide at least one new value.")
        data = copy.deepcopy(self._data)
        index = self._locate(data, expense_id)
        data["expenses"][index].update(changes)
        self._commit(data)
        return dict(data["expenses"][index])

    def delete_expense(self, expense_id):
        data = copy.deepcopy(self._data)
        index = self._locate(data, expense_id)
        removed = data["expenses"].pop(index)
        self._commit(data)
        return removed

    def list_expenses(self, sort_by="date", descending=False):
        if sort_by not in SORT_KEYS:
            raise ValidationError("Sort field must be one of: " + ", ".join(SORT_FIELDS) + ".")
        records = [dict(item) for item in self._data["expenses"]]
        return sorted(records, key=SORT_KEYS[sort_by], reverse=bool(descending))

    def search_expenses(
        self,
        keyword=None,
        category=None,
        start_date=None,
        end_date=None,
        min_amount=None,
        max_amount=None,
        sort_by="date",
        descending=False,
    ):
        text = None if is_blank(keyword) else str(keyword).strip().lower()
        wanted_category = None if is_blank(category) else validate_category(category)
        start = None if is_blank(start_date) else validate_date(start_date, allow_future=True)
        end = None if is_blank(end_date) else validate_date(end_date, allow_future=True)
        low = None if is_blank(min_amount) else validate_amount(min_amount)
        high = None if is_blank(max_amount) else validate_amount(max_amount)
        if start and end and start > end:
            raise ValidationError("Start date cannot be after end date.")
        if low is not None and high is not None and low > high:
            raise ValidationError("Minimum amount cannot be more than maximum amount.")
        results = []
        for item in self.list_expenses(sort_by, descending):
            if text and text not in item["description"].lower() and text not in item["category"].lower():
                continue
            if wanted_category and item["category"] != wanted_category:
                continue
            if start and item["date"] < start:
                continue
            if end and item["date"] > end:
                continue
            if low is not None and item["amount"] < low:
                continue
            if high is not None and item["amount"] > high:
                continue
            results.append(item)
        return results

    def daily_total(self, date_value=None):
        day = self._resolve_date(date_value, allow_future=True)
        return total_of([item for item in self._data["expenses"] if item["date"] == day])

    def monthly_total(self, month=None):
        return total_of(self._month_items(self._resolve_month(month)))

    def category_totals(self, month=None):
        if is_blank(month):
            items = self._data["expenses"]
        else:
            items = self._month_items(validate_month(month))
        totals = {}
        for item in items:
            totals[item["category"]] = totals.get(item["category"], 0.0) + item["amount"]
        ordered = sorted(totals.items(), key=lambda pair: (-pair[1], pair[0]))
        return {name: round(amount, 2) for name, amount in ordered}

    def daily_totals(self, month=None):
        totals = {}
        for item in self._month_items(self._resolve_month(month)):
            totals[item["date"]] = totals.get(item["date"], 0.0) + item["amount"]
        return {day: round(totals[day], 2) for day in sorted(totals)}

    def set_budget(self, month, amount):
        clean_month = validate_month(month)
        clean_amount = validate_amount(amount)
        data = copy.deepcopy(self._data)
        data["budgets"][clean_month] = clean_amount
        self._commit(data)
        return {"month": clean_month, "amount": clean_amount}

    def get_budget(self, month=None):
        return self._data["budgets"].get(self._resolve_month(month))

    def budget_status(self, month=None):
        clean_month = self._resolve_month(month)
        spent = total_of(self._month_items(clean_month))
        budget = self._data["budgets"].get(clean_month)
        if budget is None:
            return {
                "month": clean_month,
                "budget": None,
                "spent": spent,
                "remaining": None,
                "percent_used": None,
                "state": "no_budget",
            }
        ratio = spent / budget
        if ratio > 1:
            state = "over"
        elif ratio >= WARNING_RATIO:
            state = "warning"
        else:
            state = "ok"
        return {
            "month": clean_month,
            "budget": budget,
            "spent": spent,
            "remaining": round(budget - spent, 2),
            "percent_used": round(ratio * 100, 1),
            "state": state,
        }

    def spending_summary(self, month=None):
        clean_month = self._resolve_month(month)
        items = self._month_items(clean_month)
        total = total_of(items)
        count = len(items)
        categories = []
        for name, amount in self.category_totals(clean_month).items():
            percent = round(amount / total * 100, 1) if total else 0.0
            categories.append({"category": name, "total": amount, "percent": percent})
        highest = None
        if items:
            highest = dict(max(items, key=lambda item: (item["amount"], item["id"])))
        return {
            "month": clean_month,
            "total": total,
            "count": count,
            "average": round(total / count, 2) if count else 0.0,
            "categories": categories,
            "daily_totals": self.daily_totals(clean_month),
            "highest_expense": highest,
            "budget": self.budget_status(clean_month),
        }

    def export_to_csv(self, path, expenses=None):
        records = self.list_expenses() if expenses is None else expenses
        return export_expenses_csv(path, records)
