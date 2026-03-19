export default async function InvoiceDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold">Invoice {id}</h1>
    </div>
  );
}
