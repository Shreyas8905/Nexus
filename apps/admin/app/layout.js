import "./globals.css";

export const metadata = { title: "Nexus Admin" };

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
