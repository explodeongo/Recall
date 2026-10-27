import type { Metadata } from "next";
import { Figtree, Geist_Mono, Newsreader } from "next/font/google";
import { Nav } from "@/components/Nav";
import { Providers } from "./providers";
import "./globals.css";

// Interface text: Figtree, open and friendly, and clear at small sizes. Reading text and
// headings stay in Newsreader; code in Geist Mono.
const figtree = Figtree({ subsets: ["latin"], variable: "--font-figtree" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono" });
const newsreader = Newsreader({ subsets: ["latin"], variable: "--font-newsreader", style: ["normal", "italic"] });

export const metadata: Metadata = {
  title: { default: "Recall", template: "%s · Recall" },
  description: "Save PDFs and articles, then ask questions and get answers cited from your own library.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${figtree.variable} ${geistMono.variable} ${newsreader.variable} font-sans antialiased`}>
        <Providers>
          <Nav />
          <main className="w-full px-4 pt-8 pb-24 sm:px-6">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
