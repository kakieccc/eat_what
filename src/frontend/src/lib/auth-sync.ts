const channelName = "food-auth-changed-v1";
const source = crypto.randomUUID();

export async function withAuthLock<T>(action: () => Promise<T>): Promise<T> {
  if (!navigator.locks)
    throw new Error("当前浏览器无法安全切换账号，请升级浏览器并通过 HTTPS 访问");
  // Tabs share the Cookie; hold the lock through both mutation and session reconciliation.
  return navigator.locks.request("food-auth-session-v1", action);
}

export function notifyAuthChanged() {
  const channel = new BroadcastChannel(channelName);
  try {
    channel.postMessage(source);
  } finally {
    channel.close();
  }
}

export function watchAuthChanges(recheck: () => void) {
  const channel = new BroadcastChannel(channelName);
  channel.onmessage = (event: MessageEvent<unknown>) => {
    if (typeof event.data === "string" && event.data !== source) recheck();
  };
  return () => channel.close();
}
