import "./globals.css";

export const metadata = {
  title: "Nexus Admin",
  description: "Administration console for knowledge base ingestion and access control.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}