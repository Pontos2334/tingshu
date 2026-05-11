import { createWebHistory } from 'vue-router'

function withSuppressedHistoryPersistence(factory) {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return factory()
  }

  const originalWindowAddEventListener = window.addEventListener
  const originalDocumentAddEventListener = document.addEventListener

  window.addEventListener = function patchedWindowAddEventListener(type, listener, options) {
    if (type === 'pagehide') {
      return
    }
    return originalWindowAddEventListener.call(this, type, listener, options)
  }

  document.addEventListener = function patchedDocumentAddEventListener(type, listener, options) {
    if (type === 'visibilitychange') {
      return
    }
    return originalDocumentAddEventListener.call(this, type, listener, options)
  }

  try {
    return factory()
  } finally {
    window.addEventListener = originalWindowAddEventListener
    document.addEventListener = originalDocumentAddEventListener
  }
}

export function createStableWebHistory(base) {
  // Vue Router persists scroll state on pagehide/visibilitychange by writing
  // history.state. In this embedded browser that write causes minimized windows
  // to bounce back to the foreground, so we suppress those listeners at setup.
  return withSuppressedHistoryPersistence(() => createWebHistory(base))
}
