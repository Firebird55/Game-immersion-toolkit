import type { Metadata } from 'next';
import '../desktop/fonts.css';
import './globals.css';
import '@firebird55/lexirise-components/styles.css';

export const metadata: Metadata = {
  title: 'Game immersion toolkit',
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
        className="desktop-fonts antialiased"
      >
        {children}
      </body>
    </html>
  );
}
