import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { UploadFileModal } from "./UploadFileModal";

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderModal(onUploaded = vi.fn(), onHide = vi.fn()) {
  render(<UploadFileModal show={true} onHide={onHide} onUploaded={onUploaded} />);
  return { onUploaded, onHide };
}

describe("UploadFileModal", () => {
  it("shows a validation error when fields are empty", async () => {
    const user = userEvent.setup();
    const { onUploaded } = renderModal();

    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(screen.getByText("Укажите название и выберите файл")).toBeInTheDocument();
    expect(onUploaded).not.toHaveBeenCalled();
  });

  it("uploads the form and notifies the parent", async () => {
    const user = userEvent.setup();
    const { onUploaded, onHide } = renderModal();

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ id: "abc" }), {
          status: 201,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    await user.type(screen.getByLabelText("Название"), "Отчёт за март");
    await user.upload(screen.getByLabelText("Файл"), new File(["data"], "march.txt"));

    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(onUploaded).toHaveBeenCalledTimes(1);
    expect(onHide).toHaveBeenCalledTimes(1);

    const [, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    const body = init.body as FormData;
    expect(body.get("title")).toBe("Отчёт за март");
    expect((body.get("file") as File).name).toBe("march.txt");
  });

  it("shows a server error and does not close on failure", async () => {
    const user = userEvent.setup();
    const { onUploaded, onHide } = renderModal();

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "File is empty" }), {
          status: 400,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    await user.type(screen.getByLabelText("Название"), "x");
    await user.upload(screen.getByLabelText("Файл"), new File(["data"], "x.txt"));
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(await screen.findByText("File is empty")).toBeInTheDocument();
    expect(onUploaded).not.toHaveBeenCalled();
    expect(onHide).not.toHaveBeenCalled();
  });
});
