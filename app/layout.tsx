import type { Metadata } from 'next';
import type { CSSProperties } from 'react';
import './globals.css';

const localFonts = {
  '--font-geist-sans': '"Segoe UI", Arial, sans-serif',
  '--font-geist-mono': 'Consolas, "Courier New", monospace',
} as CSSProperties;

export const metadata: Metadata = {
  title: 'Proxy Transcript — Bilingual Game Companion',
  description: 'A local bilingual transcript companion for voiced game dialogue.',
  icons: {
    icon: '/proxy-transcript.png',
    apple: '/proxy-transcript.png',
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        suppressHydrationWarning
        className="antialiased"
        style={localFonts}
      >
        {children}
      </body>
    </html>
  );
}
