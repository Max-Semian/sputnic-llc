import type { Metadata } from "next";
import "bootstrap/dist/css/bootstrap.min.css";

export async function generateMetadata(): Promise<Metadata> {
  return {
    title: "Тестовое задание Fullstack",
    description: "Файлообменник: загрузка, проверка на подозрительный контент, алерты",
    icons: { icon: "/favicon.ico" },
  };
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
