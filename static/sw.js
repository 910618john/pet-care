// 極簡Service Worker, 只負責接收Web Push事件並顯示通知, 不做離線快取

self.addEventListener("push", (event) => {
  let payload = { title: "寵物健康管理", body: "有提醒事項", url: "/" };
  try {
    if (event.data) payload = Object.assign(payload, event.data.json());
  } catch (e) {
    // 解析失敗就用預設文字, 不要整個推播噴掉
  }
  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
      data: { url: payload.url || "/" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then(async (windowClients) => {
      for (const client of windowClients) {
        if ("focus" in client) {
          await client.focus();
          return;
        }
      }
      if (clients.openWindow) return clients.openWindow(targetUrl);
    })
  );
});
