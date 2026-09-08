import { request, resolveApiUrl } from "@/lib/apiClient";
import type { FileItem } from "@/types";

export function listFiles(): Promise<FileItem[]> {
  return request<FileItem[]>("/files");
}

export function uploadFile(title: string, file: File): Promise<FileItem> {
  const formData = new FormData();
  formData.append("title", title);
  formData.append("file", file);
  return request<FileItem>("/files", { method: "POST", body: formData });
}

export function getFileDownloadUrl(fileId: string): string {
  return resolveApiUrl(`/files/${fileId}/download`);
}
