import type { Metadata } from "next";
import localFont from "next/font/local";
import ClientProviders from "@/components/providers/ClientProviders";
import "./globals.css";

const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: "Trading Bot Dashboard",
  description: "AI-powered crypto trading bot control panel",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${geistMono.variable} antialiased`} style={{ background: "#0d0f1a" }}>
        <ClientProviders>
          {children}
        </ClientProviders>
      </body>
    </html>
  );
}
