import { describe, it, expect, vi } from "vitest";
import { BadRequestException } from "@nestjs/common";
import { SignalsController } from "./signals.controller";

/** A manual close must always book a real price. */
function make() {
  const service = {
    closeWithPrice: vi.fn().mockResolvedValue(null),
    close: vi.fn().mockResolvedValue(null),
  };
  const gateway = { emitTradeUpdate: vi.fn() };
  const telegram = { sendTradeCloseAlert: vi.fn() };
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- test doubles for the three collaborators
  const controller = new SignalsController(service as any, gateway as any, telegram as any);
  return { controller, service };
}

describe("PATCH /api/signals/:id/close", () => {
  it("books the price it is given", async () => {
    const { controller, service } = make();
    await controller.close(7, { exitPrice: "101.5" });
    expect(service.closeWithPrice).toHaveBeenCalledWith(7, 101.5);
    expect(service.close).not.toHaveBeenCalled();
  });

  it.each([0, -5, "abc", Number.NaN])("refuses the price %s", async (bad) => {
    const { controller, service } = make();
    await expect(controller.close(7, { exitPrice: bad })).rejects.toBeInstanceOf(BadRequestException);
    expect(service.closeWithPrice).not.toHaveBeenCalled();
    expect(service.close).not.toHaveBeenCalled();
  });

  it("asks the service for the live price when none is given", async () => {
    const { controller, service } = make();
    await controller.close(7, {});
    expect(service.close).toHaveBeenCalledWith(7);
    expect(service.closeWithPrice).not.toHaveBeenCalled();
  });

  it("passes on the refusal when there is no live price either", async () => {
    const { controller, service } = make();
    service.close.mockRejectedValue(new BadRequestException("No live price for ONGC right now."));
    await expect(controller.close(7, {})).rejects.toThrow("No live price");
  });
});
