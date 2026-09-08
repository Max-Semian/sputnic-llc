import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AlertsTable } from "./AlertsTable";
import { makeAlert } from "./testFixtures";

describe("AlertsTable", () => {
  it("shows an empty state", () => {
    render(<AlertsTable alerts={[]} isLoading={false} />);
    expect(screen.getByText("Алертов пока нет")).toBeInTheDocument();
  });

  it("renders alert rows with levels", () => {
    render(
      <AlertsTable
        alerts={[
          makeAlert({ level: "critical", message: "File processing failed" }),
          makeAlert({ level: "info", message: "File processed successfully" }),
        ]}
        isLoading={false}
      />,
    );

    expect(screen.getByText("File processing failed")).toBeInTheDocument();
    expect(screen.getByText("critical")).toBeInTheDocument();
    expect(screen.getByText("info")).toBeInTheDocument();
  });
});
