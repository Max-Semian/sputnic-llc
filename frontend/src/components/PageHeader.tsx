import type { ReactNode } from "react";
import { Button, Card } from "react-bootstrap";

type PageHeaderProps = {
  onRefresh: () => void;
  onAddFile: () => void;
  isRefreshing?: boolean;
  children?: ReactNode;
};

export function PageHeader({
  onRefresh,
  onAddFile,
  isRefreshing,
  children,
}: PageHeaderProps) {
  return (
    <Card className="shadow-sm border-0 mb-4">
      <Card.Body className="p-4">
        <div className="d-flex justify-content-between align-items-start gap-3 flex-wrap">
          <div>
            <h1 className="h3 mb-2">Управление файлами</h1>
            <p className="text-secondary mb-0">
              Загрузка файлов, просмотр статусов обработки и ленты алертов.
            </p>
            {children}
          </div>
          <div className="d-flex gap-2">
            <Button
              variant="outline-secondary"
              onClick={onRefresh}
              disabled={isRefreshing}
            >
              Обновить
            </Button>
            <Button variant="primary" onClick={onAddFile}>
              Добавить файл
            </Button>
          </div>
        </div>
      </Card.Body>
    </Card>
  );
}
