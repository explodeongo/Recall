import type { Metadata } from "next";
import { Geist } from "next/font/google";
import { Nav } from "@/components/Nav";
import "./globals.css";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist-sans" });

export const metadata: Metadata = {
  title: "Recall",
  description: "Save PDFs and articles, then ask questions and get answers cited from your own library.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${geist.variable} font-sans antialiased`}>
        <Nav />
        <main className="mx-auto max-w-4xl px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
