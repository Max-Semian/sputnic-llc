import { FormEvent, useState } from "react";
import { Alert, Button, Form, Modal } from "react-bootstrap";

import { useUploadFile } from "@/hooks/useUploadFile";

type UploadFileModalProps = {
  show: boolean;
  onHide: () => void;
  onUploaded: () => void;
};

/**
 * Form for uploading a new file. Submission logic lives in the
 * ``useUploadFile`` hook; this component only wires it to the modal UI.
 */
export function UploadFileModal({ show, onHide, onUploaded }: UploadFileModalProps) {
  const [title, setTitle] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const { isSubmitting, error, upload } = useUploadFile(async () => {
    setTitle("");
    setSelectedFile(null);
    setValidationError(null);
    onHide();
    onUploaded();
  });

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!title.trim() || !selectedFile) {
      setValidationError("Укажите название и выберите файл");
      return;
    }

    setValidationError(null);
    await upload(title, selectedFile);
  }

  return (
    <Modal show={show} onHide={onHide} centered>
      <Form onSubmit={handleSubmit}>
        <Modal.Header closeButton>
          <Modal.Title>Добавить файл</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {(validationError || error) && (
            <Alert variant="danger">{validationError ?? error}</Alert>
          )}
          <Form.Group className="mb-3">
            <Form.Label htmlFor="upload-title">Название</Form.Label>
            <Form.Control
              id="upload-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Например, Договор с подрядчиком"
              maxLength={255}
            />
          </Form.Group>
          <Form.Group>
            <Form.Label htmlFor="upload-file">Файл</Form.Label>
            <Form.Control
              id="upload-file"
              type="file"
              onChange={(event) =>
                setSelectedFile((event.target as HTMLInputElement).files?.[0] ?? null)
              }
            />
          </Form.Group>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="outline-secondary" onClick={onHide}>
            Отмена
          </Button>
          <Button type="submit" variant="primary" disabled={isSubmitting}>
            {isSubmitting ? "Загрузка..." : "Сохранить"}
          </Button>
        </Modal.Footer>
      </Form>
    </Modal>
  );
}
