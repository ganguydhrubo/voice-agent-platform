import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ConfirmDelete, DataTable, Field, PasswordInput, SearchInput, ToastProvider } from "../components/ui";

describe("Field", () => {
  it("marks a mandatory field with no space before the asterisk", () => {
    const { container } = render(<Field label="Full Name" required>{(props) => <input {...props} />}</Field>);
    expect(container.querySelector("label")?.textContent).toBe("Full Name*");
  });

  it("shows the error below the field", () => {
    render(<Field label="Full Name" required error="Full Name is required.">{(props) => <input {...props} />}</Field>);
    expect(screen.getByText("Full Name is required.")).toBeTruthy();
    expect(screen.getByLabelText(/Full Name/).getAttribute("aria-invalid")).toBe("true");
  });
});

describe("SearchInput", () => {
  it("has a clear button that empties the field", async () => {
    const onChange = vi.fn();
    render(<SearchInput value="abc" onChange={onChange} placeholder="Search" />);
    await userEvent.click(screen.getByRole("button"));
    expect(onChange).toHaveBeenCalledWith("");
  });
});

describe("PasswordInput", () => {
  it("shows and hides the password", async () => {
    render(<PasswordInput id="password" value="secret-1" onChange={() => undefined} />);
    const input = document.querySelector("input") as HTMLInputElement;
    expect(input.type).toBe("password");
    await userEvent.click(screen.getByRole("button"));
    expect(input.type).toBe("text");
  });
});

describe("ConfirmDelete", () => {
  it("names what will be deleted and waits for confirmation", async () => {
    const onConfirm = vi.fn();
    render(<ConfirmDelete title="Delete Agent" message="Are you sure you want to delete Agent Asha?" onConfirm={onConfirm} onClose={() => undefined} />);
    expect(screen.getByText("Are you sure you want to delete Agent Asha?")).toBeTruthy();
    expect(onConfirm).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(onConfirm).toHaveBeenCalled();
  });
});

describe("DataTable", () => {
  it("says No records found when empty", async () => {
    render(
      <ToastProvider>
        <DataTable columns={[{ header: "Name", cell: (row: { id: string }) => row.id }]} load={async () => ({ items: [], total: 0, page: 1, size: 10 })} searchPlaceholder="Search" />
      </ToastProvider>,
    );
    expect(await screen.findByText("No records found")).toBeTruthy();
  });
});
