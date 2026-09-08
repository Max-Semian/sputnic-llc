import { useState } from "react";

import { uploadFile } from "@/api/files";

export type UploadState = {
  isSubmitting: boolean;
  error: string | null;
  upload: (title: string, file: File) => Promise<boolean>;
};

/**
 * Encapsulates the "upload a file" flow used by the modal form: validation is
 * left to the form, but HTTP submission + error handling live here.
 */
export function useUploadFile(onSuccess?: () => void): UploadState {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function upload(title: string, file: File): Promise<boolean> {
    setIsSubmitting(true);
    setError(null);

    try {
      await uploadFile(title.trim(), file);
      onSuccess?.();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить файл");
      return false;
    } finally {
      setIsSubmitting(false);
    }
  }

  return { isSubmitting, error, upload };
}
