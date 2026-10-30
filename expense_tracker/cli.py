from .display import (
    format_amount,
    format_budget_status,
    format_expense_detail,
    format_expense_table,
    format_summary,
)
from .manager import NotFoundError, current_date, current_month
from .storage import StorageError
from .validators import (
    DEFAULT_CATEGORIES,
    SORT_FIELDS,
    ValidationError,
    validate_amount,
    validate_category,
    validate_date,
    validate_description,
    validate_expense_id,
    validate_month,
)

MISSING = object()

MENU = """
==============================================
        Personal Expense & Budget Tracker
==============================================
  1. Add expense
  2. View expenses
  3. Edit expense
  4. Delete expense
  5. Search / filter expenses
  6. Daily total
  7. Monthly summary
  8. Set monthly budget
  9. Budget status
 10. Export expenses to CSV
  0. Exit
----------------------------------------------
Type "cancel" at any prompt to return to the menu."""


class CancelOperation(Exception):
    pass


def parse_sort_field(value):
    field = value.strip().lower()
    if field not in SORT_FIELDS:
        raise ValidationError("Choose one of: " + ", ".join(SORT_FIELDS) + ".")
    return field


def parse_filter_date(value):
    return validate_date(value, allow_future=True)


def parse_new_description(value):
    if value.strip() == "-":
        return ""
    return validate_description(value)


def parse_text(value):
    return value


class ExpenseTrackerCLI:
    def __init__(self, manager, input_func=None, output_func=None, default_export_path="expenses_export.csv"):
        self.manager = manager
        self.read = input_func if input_func is not None else lambda prompt="": input(prompt)
        self.write = output_func if output_func is not None else lambda text="": print(text)
        self.default_export_path = str(default_export_path)
        self.actions = {
            "1": self.add_expense,
            "2": self.view_expenses,
            "3": self.edit_expense,
            "4": self.delete_expense,
            "5": self.search_expenses,
            "6": self.daily_total,
            "7": self.monthly_summary,
            "8": self.set_budget,
            "9": self.budget_status,
            "10": self.export_csv,
        }

    def ask(self, prompt, parser, blank=MISSING):
        while True:
            raw = self.read(prompt).strip()
            if raw.lower() == "cancel":
                raise CancelOperation()
            if raw == "" and blank is not MISSING:
                return blank
            try:
                return parser(raw)
            except ValidationError as error:
                self.write(f"Invalid input: {error}")

    def confirm(self, prompt):
        while True:
            answer = self.read(prompt).strip().lower()
            if answer in ("y", "yes"):
                return True
            if answer in ("", "n", "no"):
                return False
            self.write("Please answer y or n.")

    def report_budget_after(self, record):
        month = record["date"][:7]
        status = self.manager.budget_status(month)
        if status["state"] == "over":
            self.write(
                f"Alert: you are over your budget for {month} by {format_amount(-status['remaining'])}."
            )
        elif status["state"] == "warning":
            self.write(f"Warning: you have used {status['percent_used']:.1f}% of your budget for {month}.")

    def add_expense(self):
        amount = self.ask("Amount: ", validate_amount)
        self.write("Suggested categories: " + ", ".join(DEFAULT_CATEGORIES))
        category = self.ask("Category: ", validate_category)
        description = self.ask("Description (optional): ", validate_description, blank="")
        when = self.ask("Date YYYY-MM-DD (blank for today): ", validate_date, blank=None)
        record = self.manager.add_expense(amount, category, description, when)
        self.write(
            f"Expense #{record['id']} added: {format_amount(record['amount'])} "
            f"for {record['category']} on {record['date']}."
        )
        self.report_budget_after(record)

    def view_expenses(self):
        sort_by = self.ask(
            "Sort by " + "/".join(SORT_FIELDS) + " (blank for date): ",
            parse_sort_field,
            blank="date",
        )
        descending = self.confirm("Show highest/newest first? (y/N): ")
        self.write(format_expense_table(self.manager.list_expenses(sort_by, descending)))

    def edit_expense(self):
        expense_id = self.ask("Expense ID to edit: ", validate_expense_id)
        current = self.manager.get_expense(expense_id)
        self.write(format_expense_detail(current))
        self.write("Press Enter to keep the current value.")
        amount = self.ask("New amount: ", validate_amount, blank=None)
        category = self.ask("New category: ", validate_category, blank=None)
        description = self.ask("New description (- to clear): ", parse_new_description, blank=None)
        when = self.ask("New date YYYY-MM-DD: ", validate_date, blank=None)
        updated = self.manager.edit_expense(expense_id, amount, category, description, when)
        self.write("Expense updated:")
        self.write(format_expense_detail(updated))
        self.report_budget_after(updated)

    def delete_expense(self):
        expense_id = self.ask("Expense ID to delete: ", validate_expense_id)
        current = self.manager.get_expense(expense_id)
        self.write(format_expense_detail(current))
        if self.confirm("Delete this expense? (y/N): "):
            self.manager.delete_expense(expense_id)
            self.write(f"Expense #{expense_id} deleted.")
        else:
            self.write("Deletion cancelled.")

    def search_expenses(self):
        self.write("Leave a filter blank to skip it.")
        keyword = self.ask("Keyword in description or category: ", parse_text, blank=None)
        category = self.ask("Category: ", validate_category, blank=None)
        start = self.ask("From date YYYY-MM-DD: ", parse_filter_date, blank=None)
        end = self.ask("To date YYYY-MM-DD: ", parse_filter_date, blank=None)
        low = self.ask("Minimum amount: ", validate_amount, blank=None)
        high = self.ask("Maximum amount: ", validate_amount, blank=None)
        results = self.manager.search_expenses(
            keyword=keyword,
            category=category,
            start_date=start,
            end_date=end,
            min_amount=low,
            max_amount=high,
        )
        self.write(format_expense_table(results))

    def daily_total(self):
        day = self.ask("Date YYYY-MM-DD (blank for today): ", parse_filter_date, blank=None)
        resolved = day or current_date()
        total = self.manager.daily_total(resolved)
        entries = self.manager.search_expenses(start_date=resolved, end_date=resolved)
        self.write(f"Total spent on {resolved}: {format_amount(total)}")
        if entries:
            self.write(format_expense_table(entries))

    def monthly_summary(self):
        month = self.ask("Month YYYY-MM (blank for current month): ", validate_month, blank=None)
        self.write(format_summary(self.manager.spending_summary(month)))

    def set_budget(self):
        month = self.ask("Month YYYY-MM (blank for current month): ", validate_month, blank=None)
        amount = self.ask("Budget amount: ", validate_amount)
        result = self.manager.set_budget(month or current_month(), amount)
        self.write(f"Budget for {result['month']} set to {format_amount(result['amount'])}.")
        self.write(format_budget_status(self.manager.budget_status(result["month"])))

    def budget_status(self):
        month = self.ask("Month YYYY-MM (blank for current month): ", validate_month, blank=None)
        self.write(format_budget_status(self.manager.budget_status(month)))

    def export_csv(self):
        path = self.ask(
            f"Export file path (blank for {self.default_export_path}): ",
            parse_text,
            blank=self.default_export_path,
        )
        count = len(self.manager.list_expenses())
        written = self.manager.export_to_csv(path)
        self.write(f"Exported {count} expense(s) to {written}")

    def run(self):
        while True:
            self.write(MENU)
            choice = self.read("Choose an option: ").strip()
            if choice == "0":
                self.write("Goodbye!")
                return
            action = self.actions.get(choice)
            if action is None:
                self.write("Invalid option. Please enter a number from 0 to 10.")
                continue
            try:
                action()
            except CancelOperation:
                self.write("Cancelled.")
            except (ValidationError, NotFoundError, StorageError) as error:
                self.write(f"Error: {error}")
