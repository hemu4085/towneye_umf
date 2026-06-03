const STORAGE_PREFIX = 'towneye_portal_chat_';

function storageKey(parcelId) {
  return `${STORAGE_PREFIX}${parcelId}`;
}

export function loadChatMessages(parcelId) {
  if (!parcelId) return [];
  try {
    const raw = sessionStorage.getItem(storageKey(parcelId));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((m) => m?.role && m?.content);
  } catch {
    return [];
  }
}

export function storeChatMessages(parcelId, messages) {
  if (!parcelId) return;
  try {
    if (!messages?.length) {
      sessionStorage.removeItem(storageKey(parcelId));
    } else {
      sessionStorage.setItem(storageKey(parcelId), JSON.stringify(messages));
    }
  } catch {
    /* private mode / quota */
  }
}
