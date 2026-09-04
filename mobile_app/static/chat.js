(function () {
  const feed = document.getElementById("chat-feed");
  if (!feed) {
    return;
  }

  const roomId = feed.dataset.roomId;
  if (!roomId) {
    return;
  }

  const renderMessages = (messages) => {
    if (!Array.isArray(messages) || messages.length === 0) {
      return;
    }

    const scrollDistance = feed.scrollHeight - feed.scrollTop - feed.clientHeight;
    const shouldStickToBottom = scrollDistance < 36;

    feed.innerHTML = messages
      .map((message) => {
        const safeAuthor = String(message.author || "Сотрудник");
        const safeTime = String(message.created_at || "");
        const safeBody = String(message.body || "")
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/\n/g, "<br>");
        return `
          <article class="message-item">
            <div class="message-meta">
              <strong>${safeAuthor}</strong>
              <span>${safeTime}</span>
            </div>
            <div class="message-body">${safeBody}</div>
          </article>
        `;
      })
      .join("");

    if (shouldStickToBottom) {
      feed.scrollTop = feed.scrollHeight;
    }
  };

  const loadMessages = async () => {
    try {
      const response = await fetch(`/mobile/api/chat/messages?room_id=${encodeURIComponent(roomId)}`, {
        headers: { "X-Requested-With": "fetch" },
        cache: "no-store",
      });
      if (!response.ok) {
        return;
      }
      const payload = await response.json();
      renderMessages(payload.messages || []);
    } catch (_err) {
      // Quiet polling failure: next tick will retry.
    }
  };

  loadMessages();
  setInterval(loadMessages, 5000);
})();
