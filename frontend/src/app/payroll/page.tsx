import Link from "next/link";

export default function PayrollPage() {
  return (
    <div className="p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Payroll</h1>
        <Link
          href="/payroll/new"
          className="rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
        >
          New Payroll Run
        </Link>
      </div>
    </div>
  );
}
