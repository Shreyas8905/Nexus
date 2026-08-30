import "./globals.css";

export const metadata = {
  title: "Nexus",
  description: "Local knowledge assistant",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
