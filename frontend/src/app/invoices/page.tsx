import Link from "next/link";

export default function InvoicesPage() {
  return (
    <div className="p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Invoices</h1>
        <Link
          href="/invoices/new"
          className="rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
        >
          New Invoice
        </Link>
      </div>
    </div>
  );
}
