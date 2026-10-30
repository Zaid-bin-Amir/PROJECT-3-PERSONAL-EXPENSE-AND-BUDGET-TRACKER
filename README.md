# Personal Expense & Budget Tracker

A command-line Python application to record daily expenses, organize them into categories, set monthly budgets and see spending summaries. All data is stored in a local JSON file, so nothing needs to be installed beyond Python.

## Features

- Add, edit, delete and view expenses
- Category-wise expense management (any category name, with suggestions)
- Monthly budget with usage percentage and over-budget alerts
- Daily, monthly and category-wise totals
- Monthly spending summary (total, average, highest expense, category shares, day-by-day totals)
- Search and filter by keyword, category, date range and amount range
- Sorting by date, amount, category or ID
- Export all expenses to a CSV file
- Input validation for amount, date, month, category and description
- Safe JSON storage: atomic writes, automatic backup of a damaged data file
- Unit tests for validation, storage, business logic and the menu flow

## Requirements

- Python 3.8 or newer
- No third-party packages

## Run

```
python main.py
```

On Windows you can also use `py main.py`.

## Menu

```
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
```

Tips:

- Type `cancel` at any prompt to go back to the menu.
- In the edit screen, press Enter to keep the current value, or type `-` to clear the description.
- In search, leave any filter blank to skip it.
- Dates use `YYYY-MM-DD` (for example `2026-10-30`), months use `YYYY-MM` (for example `2026-10`). A blank date means today and a blank month means the current month.

## Validation rules

| Field | Rule |
| --- | --- |
| Amount | A number greater than 0 and at most 10,000,000. Commas are allowed (`1,200.50`). Rounded to 2 decimals. |
| Date | A real date in `YYYY-MM-DD` format, year 2000 or later, not in the future when adding or editing. |
| Month | A real month in `YYYY-MM` format. |
| Category | Starts with a letter, up to 30 characters, letters, spaces, `&` and `-` only. Stored in Title Case. |
| Description | Optional, up to 100 characters. |

## Project structure

```
personal-expense-tracker/
├── main.py                  entry point
├── expense_tracker/
│   ├── cli.py               menu and user interaction
│   ├── manager.py           add, edit, delete, search, totals, budgets
│   ├── storage.py           JSON storage and CSV export
│   ├── validators.py        input validation
│   └── display.py           tables and report formatting
├── tests/
│   └── test_tracker.py      unit tests
├── data/                    expenses.json is created here on first save
├── .gitignore
└── README.md
```

## Data storage

Expenses and budgets are saved to `data/expenses.json` after every change:

```json
{
  "next_id": 3,
  "expenses": [
    {
      "id": 1,
      "date": "2026-10-30",
      "category": "Food",
      "amount": 450.0,
      "description": "Lunch"
    }
  ],
  "budgets": {
    "2026-10": 30000.0
  }
}
```

- Writes are atomic, so a crash while saving cannot leave a half-written file.
- If the file is damaged, it is renamed to `expenses.json.corrupt` and the app starts with empty data.
- To keep the data somewhere else, set the `EXPENSE_TRACKER_DATA_DIR` environment variable to a folder path before running.

## Budget alerts

A budget status is one of:

- Within budget: less than 80% used
- Warning: 80% to 100% used
- Over budget: more than 100% used

An alert is also shown right after adding or editing an expense that pushes a month into the warning or over-budget state.

## Run the tests

```
python -m unittest discover -s tests -t . -v
```

## Using Git and GitHub

```
git init
git add .
git commit -m "Personal Expense & Budget Tracker"
git branch -M main
git remote add origin https://github.com/<your-username>/personal-expense-tracker.git
git push -u origin main
```

The `.gitignore` file keeps your personal expense data out of the repository.

## Python concepts practiced

- Functions and classes with separated responsibilities
- Collections: lists, dictionaries, tuples and sets
- File handling with JSON and CSV
- Date and time handling with `datetime`
- Exception handling with custom exceptions
- Basic data processing: filtering, sorting, grouping and totals
