/**
 * Aparece na hora em que alguém troca de aba ou filtra, enquanto o servidor
 * monta a página (a lista de voos leva alguns segundos). Sem isso o clique
 * parecia não ter pegado.
 */
export default function Carregando() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Carregando">
      <div className="space-y-2">
        <div className="h-7 w-48 animate-pulse rounded bg-gray-200/70 motion-reduce:animate-none" />
        <div className="h-4 w-72 animate-pulse rounded bg-gray-200/50 motion-reduce:animate-none" />
      </div>
      <div className="overflow-hidden rounded-lg border border-gray-200 bg-white/90">
        {Array.from({ length: 8 }, (_, i) => (
          <div key={i} className="flex items-center gap-4 border-b border-gray-100 px-3 py-3 last:border-0">
            <div className="h-5 w-16 animate-pulse rounded-full bg-gray-200/70 motion-reduce:animate-none" />
            <div className="h-4 w-20 animate-pulse rounded bg-gray-200/60 motion-reduce:animate-none" />
            <div className="h-4 flex-1 animate-pulse rounded bg-gray-200/40 motion-reduce:animate-none" />
            <div className="h-7 w-24 animate-pulse rounded-md bg-gray-200/60 motion-reduce:animate-none" />
          </div>
        ))}
      </div>
    </div>
  );
}
