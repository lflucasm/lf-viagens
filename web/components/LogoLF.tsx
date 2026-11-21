import Image from "next/image";

/**
 * Marca oficial da LF Viagens — o recorte do globo com o avião, mesmo
 * arquivo usado no cabeçalho da extensão (Extensão/static/lf-icone.png,
 * copiado pra web/public/lf-icone.jpg: o conteúdo já é JPEG apesar da
 * extensão original).
 */
export function LogoLF({ size = 28, className = "" }: { size?: number; className?: string }) {
  return (
    <Image
      src="/lf-icone.jpg"
      alt="LF Viagens"
      width={size}
      height={size}
      className={`rounded-md object-cover ${className}`}
    />
  );
}
