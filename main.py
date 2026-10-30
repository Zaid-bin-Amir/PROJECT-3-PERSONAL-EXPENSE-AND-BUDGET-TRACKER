import os
import sys
from pathlib import Path

from expense_tracker.cli import ExpenseTrackerCLI
from expense_tracker.manager import ExpenseManager
from expense_tracker.storage import JsonStorage, StorageError

DATA_DIR_ENV = "EXPENSE_TRACKER_DATA_DIR"


def resolve_data_dir():
    custom = os.environ.get(DATA_DIR_ENV)
    if custom:
        return Path(custom).expanduser()
    return Path(__file__).resolve().parent / "data"


def main():
    data_dir = resolve_data_dir()
    storage = JsonStorage(data_dir / "expenses.json")
    try:
        manager = ExpenseManager(storage)
    except StorageError as error:
        print(f"Error: {error}")
        return 1
    cli = ExpenseTrackerCLI(manager, default_export_path=data_dir / "expenses_export.csv")
    try:
        cli.run()
    except (EOFError, KeyboardInterrupt):
        print("\nGoodbye!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
