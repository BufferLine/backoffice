export default async function PayrollDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold">Payroll Run {id}</h1>
    </div>
  );
}
