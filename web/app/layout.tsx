import type { Metadata } from "next";
import { Fraunces, Instrument_Sans, Geist_Mono } from "next/font/google";
import "./globals.css";

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
});

const instrumentSans = Instrument_Sans({
  variable: "--font-instrument-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "LF Viagens",
  description: "Painel de monitoramento de voos da LF Viagens",
};

const SCRIPT_TEMA = `try{var t=localStorage.getItem('lf-tema');if(t==='light'||t==='dark'){document.documentElement.setAttribute('data-theme',t)}}catch(e){}`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="pt-BR"
      suppressHydrationWarning
      className={`${fraunces.variable} ${instrumentSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        {/* Aplica a escolha de tema salva antes da 1ª pintura — sem isso a
            página nasce clara (ou no tema do sistema) e pisca pro tema
            escolhido só depois que o React hidrata. */}
        <script dangerouslySetInnerHTML={{ __html: SCRIPT_TEMA }} />
      </head>
      <body className="min-h-full flex flex-col bg-canvas text-gray-900">{children}</body>
    </html>
  );
}
