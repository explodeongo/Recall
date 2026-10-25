import type { Metadata } from "next";
import { Geist, Geist_Mono, Newsreader } from "next/font/google";
import { Nav } from "@/components/Nav";
import { Providers } from "./providers";
import "./globals.css";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono" });
const newsreader = Newsreader({ subsets: ["latin"], variable: "--font-newsreader", style: ["normal", "italic"] });

export const metadata: Metadata = {
  title: { default: "Recall", template: "%s · Recall" },
  description: "Save PDFs and articles, then ask questions and get answers cited from your own library.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${geist.variable} ${geistMono.variable} ${newsreader.variable} font-sans antialiased`}>
        <Providers>
          <Nav />
          <main className="w-full px-4 pt-8 pb-24 sm:px-6">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
