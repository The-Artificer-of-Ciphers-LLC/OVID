import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Button from "@/components/Button";
import Input from "@/components/Input";
import Field from "@/components/Field";

// ---------------------------------------------------------------------------
// Button
// ---------------------------------------------------------------------------

describe("Button", () => {
  it("carries a focus-visible ring class and forwards data-testid", () => {
    render(<Button data-testid="my-button">Click me</Button>);
    const btn = screen.getByTestId("my-button");
    expect(btn.className).toContain("focus-visible:ring");
  });

  it("is reachable via Tab and activates onClick with Enter", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <Button data-testid="my-button" onClick={onClick}>
        Go
      </Button>,
    );

    await user.tab();
    expect(screen.getByTestId("my-button")).toHaveFocus();

    await user.keyboard("{Enter}");
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("activates onClick with Space", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <Button data-testid="my-button" onClick={onClick}>
        Go
      </Button>,
    );

    await user.tab();
    await user.keyboard(" ");
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("does not fire onClick when disabled", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <Button data-testid="my-button" onClick={onClick} disabled>
        Go
      </Button>,
    );

    const btn = screen.getByTestId("my-button");
    expect(btn).toBeDisabled();
    await user.click(btn);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("never applies the accent fill to the ghost variant", () => {
    render(
      <Button data-testid="ghost-button" variant="ghost">
        Ghost
      </Button>,
    );
    const btn = screen.getByTestId("ghost-button");
    expect(btn.className).not.toContain("bg-blue-600");
  });
});

// ---------------------------------------------------------------------------
// Input
// ---------------------------------------------------------------------------

describe("Input", () => {
  it("carries a focus-visible ring class and forwards data-testid", () => {
    render(<Input data-testid="my-input" />);
    const input = screen.getByTestId("my-input");
    expect(input.className).toContain("focus-visible:ring");
  });

  it("is reachable via Tab", async () => {
    const user = userEvent.setup();
    render(<Input data-testid="my-input" />);

    await user.tab();
    expect(screen.getByTestId("my-input")).toHaveFocus();
  });
});

// ---------------------------------------------------------------------------
// Field
// ---------------------------------------------------------------------------

describe("Field", () => {
  it("associates the label with the control via htmlFor/id", () => {
    render(
      <Field id="email" label="Email">
        <Input id="email" data-testid="email-input" />
      </Field>,
    );

    const label = screen.getByText("Email");
    expect(label.tagName).toBe("LABEL");
    expect(label.getAttribute("for")).toBe("email");
    expect(screen.getByTestId("email-input").id).toBe("email");
  });

  it("renders an aria-live=polite region when an error is passed", () => {
    render(
      <Field id="email" label="Email" error="Email is required">
        <Input id="email" data-testid="email-input" />
      </Field>,
    );

    const err = screen.getByText("Email is required");
    expect(err.getAttribute("aria-live")).toBe("polite");
  });

  it("renders no error region when error is absent", () => {
    render(
      <Field id="email" label="Email">
        <Input id="email" data-testid="email-input" />
      </Field>,
    );

    expect(screen.queryByText("Email is required")).toBeNull();
  });
});
