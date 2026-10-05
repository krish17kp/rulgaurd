import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Home from "./page";
import { ApiError } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, getHealth: vi.fn() };
});

import { getHealth } from "@/lib/api";

describe("Home", () => {
  beforeEach(() => {
    vi.mocked(getHealth).mockReset();
  });

  it("shows a primary CTA that links to /upload", async () => {
    vi.mocked(getHealth).mockResolvedValue({ status: "ok", models_loaded: { rul_extra_trees: true } });
    render(<Home />);

    const cta = screen.getByRole("link", { name: /analyze bearing data/i });
    expect(cta).toHaveAttribute("href", "/upload");
    await waitFor(() => expect(screen.getByText("ok")).toBeInTheDocument());
  });

  it("shows prediction service status once health resolves", async () => {
    vi.mocked(getHealth).mockResolvedValue({ status: "ok", models_loaded: {} });
    render(<Home />);
    await waitFor(() => expect(screen.getByText("ok")).toBeInTheDocument());
  });

  it("never fabricates a status when health is unreachable", async () => {
    vi.mocked(getHealth).mockRejectedValue(new ApiError(0, "unreachable"));
    render(<Home />);
    await waitFor(() => expect(screen.getByText(/unreachable/)).toBeInTheDocument());
  });
});
