CURRENCY = "Rs"
DESCRIPTION_WIDTH = 40
BAR_WIDTH = 20
LINE_WIDTH = 44


def format_amount(value):
    return f"{CURRENCY} {value:,.2f}"


def truncate(text, width):
    if len(text) <= width:
        return text
    return text[: width - 3] + "..."


def render_table(headers, rows, right_aligned=()):
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def render(cells):
        parts = []
        for index, cell in enumerate(cells):
            if index in right_aligned:
                parts.append(cell.rjust(widths[index]))
            else:
                parts.append(cell.ljust(widths[index]))
        return "  ".join(parts).rstrip()

    lines = [render(headers), "  ".join("-" * width for width in widths)]
    lines.extend(render(row) for row in rows)
    return "\n".join(lines)


def format_expense_table(expenses):
    if not expenses:
        return "No expenses found."
    rows = [
        (
            str(item["id"]),
            item["date"],
            item["category"],
            format_amount(item["amount"]),
            truncate(item["description"], DESCRIPTION_WIDTH),
        )
        for item in expenses
    ]
    table = render_table(
        ("ID", "Date", "Category", "Amount", "Description"),
        rows,
        right_aligned=(0, 3),
    )
    total = round(sum(item["amount"] for item in expenses), 2)
    return f"{table}\n\n{len(expenses)} expense(s), total {format_amount(total)}"


def format_expense_detail(expense):
    description = expense["description"] or "-"
    return "\n".join(
        [
            f"  ID          : {expense['id']}",
            f"  Date        : {expense['date']}",
            f"  Category    : {expense['category']}",
            f"  Amount      : {format_amount(expense['amount'])}",
            f"  Description : {description}",
        ]
    )


def format_category_totals(totals):
    if not totals:
        return "No expenses found."
    grand_total = sum(totals.values())
    rows = []
    for name, amount in totals.items():
        percent = amount / grand_total * 100 if grand_total else 0.0
        rows.append((name, format_amount(amount), f"{percent:.1f}%"))
    return render_table(("Category", "Total", "Share"), rows, right_aligned=(1, 2))


def format_budget_status(status):
    month = status["month"]
    if status["state"] == "no_budget":
        return f"No budget set for {month}. Spent so far: {format_amount(status['spent'])}."
    lines = [
        f"Budget for {month}",
        f"  Budget    : {format_amount(status['budget'])}",
        f"  Spent     : {format_amount(status['spent'])}",
    ]
    if status["remaining"] >= 0:
        lines.append(f"  Remaining : {format_amount(status['remaining'])}")
    else:
        lines.append(f"  Over by   : {format_amount(-status['remaining'])}")
    lines.append(f"  Used      : {status['percent_used']:.1f}%")
    if status["state"] == "over":
        lines.append("Alert: you have exceeded your budget.")
    elif status["state"] == "warning":
        lines.append("Warning: you have used 80% or more of your budget.")
    else:
        lines.append("You are within your budget.")
    return "\n".join(lines)


def format_summary(summary):
    lines = [f"Spending summary for {summary['month']}", "-" * LINE_WIDTH]
    if summary["count"] == 0:
        lines.append("No expenses recorded for this month.")
    else:
        highest = summary["highest_expense"]
        lines.append(f"Total spent       : {format_amount(summary['total'])}")
        lines.append(f"Expenses recorded : {summary['count']}")
        lines.append(f"Average expense   : {format_amount(summary['average'])}")
        lines.append(
            f"Highest expense   : {format_amount(highest['amount'])} "
            f"({highest['category']}, {highest['date']})"
        )
        category_rows = []
        for entry in summary["categories"]:
            filled = round(entry["percent"] / 100 * BAR_WIDTH)
            if entry["percent"] > 0:
                filled = max(1, filled)
            category_rows.append(
                (
                    entry["category"],
                    format_amount(entry["total"]),
                    f"{entry['percent']:.1f}%",
                    "#" * filled,
                )
            )
        lines.append("")
        lines.append("By category:")
        lines.append(
            render_table(("Category", "Total", "Share", ""), category_rows, right_aligned=(1, 2))
        )
        day_rows = [(day, format_amount(amount)) for day, amount in summary["daily_totals"].items()]
        lines.append("")
        lines.append("By day:")
        lines.append(render_table(("Date", "Total"), day_rows, right_aligned=(1,)))
    lines.append("")
    lines.append(format_budget_status(summary["budget"]))
    return "\n".join(lines)
