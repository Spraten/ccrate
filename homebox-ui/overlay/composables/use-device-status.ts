let activeDeviceRequest: Promise<unknown> | null = null;

export async function serializedDeviceRequest<T>(request: () => Promise<T>, current: () => boolean): Promise<T | undefined> {
  while (activeDeviceRequest) {
    const pending = activeDeviceRequest;
    try { await pending; } catch { /* The next current request may still run. */ }
    if (!current()) return;
  }
  if (!current()) return;
  const pending = request();
  activeDeviceRequest = pending;
  try { return await pending; }
  finally { if (activeDeviceRequest === pending) activeDeviceRequest = null; }
}
