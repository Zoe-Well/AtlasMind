import { describe, expect, it } from "vitest";

import {
  cameraRatioToZoomPercent,
  MAX_ZOOM_PERCENT,
  MIN_ZOOM_PERCENT,
  zoomPercentToCameraRatio,
} from "./graph-camera";

describe("graph camera zoom conversion", () => {
  it("converts camera ratios to user-facing percentages", () => {
    expect(cameraRatioToZoomPercent(1)).toBe(100);
    expect(cameraRatioToZoomPercent(0.5)).toBe(200);
    expect(cameraRatioToZoomPercent(2)).toBe(50);
  });

  it("clamps direct percentage input to supported camera limits", () => {
    expect(zoomPercentToCameraRatio(1)).toBeCloseTo(100 / MIN_ZOOM_PERCENT);
    expect(zoomPercentToCameraRatio(5000)).toBeCloseTo(100 / MAX_ZOOM_PERCENT);
  });
});
