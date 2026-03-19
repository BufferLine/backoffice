import Link from "next/link";

export default function ExpensesPage() {
  return (
    <div className="p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Expenses</h1>
        <Link
          href="/expenses/new"
          className="rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
        >
          Add Expense
        </Link>
      </div>
    </div>
  );
}
