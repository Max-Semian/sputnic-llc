import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FilesTable } from "./FilesTable";
import { makeFile } from "./testFixtures";

describe("FilesTable", () => {
  it("shows an empty state", () => {
    render(<FilesTable files={[]} isLoading={false} />);
    expect(screen.getByText("Файлы пока не загружены")).toBeInTheDocument();
  });

  it("renders file rows with metadata", () => {
    render(
      <FilesTable
        files={[makeFile({ id: "file-1", title: "Договор", original_name: "doc.txt" })]}
        isLoading={false}
      />,
    );

    expect(screen.getByText("Договор")).toBeInTheDocument();
    expect(screen.getByText("doc.txt")).toBeInTheDocument();
    expect(screen.getByText("clean")).toBeInTheDocument();
    expect(screen.getByText("processed")).toBeInTheDocument();

    const download = screen.getByRole("link", { name: "Скачать" });
    expect(download.getAttribute("href")).toContain("/files/file-1/download");
  });

  it("shows a spinner while loading", () => {
    render(<FilesTable files={[]} isLoading={true} />);
    expect(document.querySelector(".spinner-border")).not.toBeNull();
  });
});

