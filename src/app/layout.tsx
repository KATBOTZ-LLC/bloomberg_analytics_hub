import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CFO Dashboard Frontend Prototype",
  description: "Next.js prototype for Apple-inspired CFO dashboard UI with WebGL and dynamic tile layouts.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
