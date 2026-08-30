export const MIN_ZOOM_PERCENT = 13;
export const MAX_ZOOM_PERCENT = 1250;

export function clampZoomPercent(value: number) {
  if (!Number.isFinite(value)) return 100;
  return Math.min(MAX_ZOOM_PERCENT, Math.max(MIN_ZOOM_PERCENT, Math.round(value)));
}

export function cameraRatioToZoomPercent(ratio: number) {
  if (!Number.isFinite(ratio) || ratio <= 0) return 100;
  return clampZoomPercent(100 / ratio);
}

export function zoomPercentToCameraRatio(percent: number) {
  return 100 / clampZoomPercent(percent);
}
