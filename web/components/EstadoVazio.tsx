/** Tela sem itens: diz o que está vazio e quando algo vai aparecer ali. */
export function EstadoVazio({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-gray-300 bg-white/90 px-6 py-10 text-center">
      <p className="font-medium text-gray-800">{titulo}</p>
      <p className="mx-auto mt-1 max-w-md text-sm text-gray-500">{children}</p>
    </div>
  );
}
