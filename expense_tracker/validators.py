import math
import re
from datetime import date, datetime

DATE_FORMAT = "%Y-%m-%d"
MONTH_FORMAT = "%Y-%m"
MIN_YEAR = 2000
MAX_AMOUNT = 10_000_000
MAX_CATEGORY_LENGTH = 30
MAX_DESCRIPTION_LENGTH = 100
SORT_FIELDS = ("date", "amount", "category", "id")
DEFAULT_CATEGORIES = (
    "Food",
    "Transport",
    "Bills",
    "Shopping",
    "Health",
    "Education",
    "Entertainment",
    "Other",
)

AMOUNT_PATTERN = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)$")
CATEGORY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z &\-]*$")


class ValidationError(ValueError):
    pass


def validate_amount(value):
    if isinstance(value, bool):
        raise ValidationError("Amount must be a number.")
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            raise ValidationError("Amount cannot be empty.")
        if not AMOUNT_PATTERN.match(text):
            raise ValidationError("Amount must be a valid number, for example 250 or 1200.50.")
        number = float(text)
    elif isinstance(value, (int, float)):
        number = float(value)
    else:
        raise ValidationError("Amount must be a number.")
    if not math.isfinite(number):
        raise ValidationError("Amount must be a finite number.")
    number = round(number, 2)
    if number <= 0:
        raise ValidationError("Amount must be greater than zero.")
    if number > MAX_AMOUNT:
        raise ValidationError(f"Amount cannot be more than {MAX_AMOUNT:,}.")
    return number


def validate_date(value, allow_future=False):
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValidationError("Date cannot be empty.")
        try:
            parsed = datetime.strptime(text, DATE_FORMAT).date()
        except ValueError:
            raise ValidationError("Date must be a real date in YYYY-MM-DD format.") from None
    else:
        raise ValidationError("Date must be in YYYY-MM-DD format.")
    if parsed.year < MIN_YEAR:
        raise ValidationError(f"Date must be in the year {MIN_YEAR} or later.")
    if not allow_future and parsed > date.today():
        raise ValidationError("Date cannot be in the future.")
    return parsed.strftime(DATE_FORMAT)


def validate_month(value):
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValidationError("Month cannot be empty.")
        try:
            parsed = datetime.strptime(text, MONTH_FORMAT)
        except ValueError:
            raise ValidationError("Month must be a real month in YYYY-MM format.") from None
    else:
        raise ValidationError("Month must be in YYYY-MM format.")
    if parsed.year < MIN_YEAR:
        raise ValidationError(f"Month must be in the year {MIN_YEAR} or later.")
    return parsed.strftime(MONTH_FORMAT)


def validate_category(value):
    if not isinstance(value, str):
        raise ValidationError("Category must be text.")
    text = " ".join(value.split())
    if not text:
        raise ValidationError("Category cannot be empty.")
    if len(text) > MAX_CATEGORY_LENGTH:
        raise ValidationError(f"Category cannot be longer than {MAX_CATEGORY_LENGTH} characters.")
    if not CATEGORY_PATTERN.match(text):
        raise ValidationError("Category must start with a letter and use only letters, spaces, & or -.")
    return text.title()


def validate_description(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValidationError("Description must be text.")
    text = " ".join(value.split())
    if len(text) > MAX_DESCRIPTION_LENGTH:
        raise ValidationError(f"Description cannot be longer than {MAX_DESCRIPTION_LENGTH} characters.")
    return text


def validate_expense_id(value):
    if isinstance(value, bool):
        raise ValidationError("Expense ID must be a whole number.")
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValidationError("Expense ID must be a whole number.") from None
    if number < 1:
        raise ValidationError("Expense ID must be a positive number.")
    return number
