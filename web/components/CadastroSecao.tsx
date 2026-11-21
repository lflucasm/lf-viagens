/** Blocos visuais reaproveitados pelos formulários públicos de cadastro do cedente (convite e cadastro guiado). */
export const INPUT_CLASSE =
  "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-gold-500 focus:outline-none focus:ring-2 focus:ring-gold-400/40";

export function Secao({
  titulo,
  descricao,
  children,
}: {
  titulo: string;
  descricao?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-3 rounded-xl border border-gray-100 bg-white/90 p-5 shadow-sm">
      <div>
        <h2 className="text-sm font-semibold text-gray-900">{titulo}</h2>
        {descricao && <p className="text-xs text-gray-500">{descricao}</p>}
      </div>
      <div className="grid gap-3 sm:grid-cols-2">{children}</div>
    </section>
  );
}

export function Campo({
  label,
  className = "",
  children,
}: {
  label: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <label className={`block space-y-1 ${className}`}>
      <span className="block text-xs font-medium text-gray-600">{label}</span>
      {children}
    </label>
  );
}
