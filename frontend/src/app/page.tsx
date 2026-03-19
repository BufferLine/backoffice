export default function DashboardPage() {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold">Dashboard</h1>
      <div className="mt-6 grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
        <div className="rounded-lg border p-6">
          <h2 className="text-sm font-medium text-gray-500">Outstanding Invoices</h2>
          <p className="mt-2 text-3xl font-bold">-</p>
        </div>
        <div className="rounded-lg border p-6">
          <h2 className="text-sm font-medium text-gray-500">Payroll Status</h2>
          <p className="mt-2 text-3xl font-bold">-</p>
        </div>
        <div className="rounded-lg border p-6">
          <h2 className="text-sm font-medium text-gray-500">Pending Expenses</h2>
          <p className="mt-2 text-3xl font-bold">-</p>
        </div>
      </div>
    </div>
  );
}
