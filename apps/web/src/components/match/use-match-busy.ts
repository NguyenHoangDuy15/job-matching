"use client";

import { useSyncExternalStore } from "react";

// Thanh lọc và vùng kết quả là hai component anh em do trang server dựng:
// vùng kết quả báo "đang chấm" qua đây để thanh lọc khóa nút Tìm (API giới hạn 20 lượt/phút).
let busy = false;
const listeners = new Set<() => void>();

export function setMatchBusy(value: boolean) {
  if (busy === value) return;
  busy = value;
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useMatchBusy(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => busy,
    () => false,
  );
}
