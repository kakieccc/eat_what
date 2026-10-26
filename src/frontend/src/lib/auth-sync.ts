const channelName = "food-auth-changed-v1";
const source = crypto.randomUUID();

function openChannel() {
  try {
    return typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel(channelName);
  } catch {
    return null;
  }
}

export function notifyAuthChanged() {
  const channel = openChannel();
  if (channel) {
    try {
      channel.postMessage(source);
      return;
    } catch {
      // Fall back to storage if the channel cannot send.
    } finally {
      channel.close();
    }
  }
  try {
    localStorage.setItem(channelName, crypto.randomUUID());
  } catch {
    // Storage can be disabled by browser privacy settings.
  }
}

export function watchAuthChanges(recheck: () => void) {
  const channel = openChannel();
  if (channel) {
    channel.onmessage = (event: MessageEvent<unknown>) => {
      if (typeof event.data === "string" && event.data !== source) recheck();
    };
  }
  const onStorage = (event: StorageEvent) => {
    if (event.storageArea === localStorage && event.key === channelName && event.newValue !== null)
      recheck();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    channel?.close();
    window.removeEventListener("storage", onStorage);
  };
}
