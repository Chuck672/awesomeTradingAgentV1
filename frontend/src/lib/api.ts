export function getBaseUrl() {
  if (typeof window !== 'undefined') {
    if (window.location.protocol === 'app:') {
      return "http://localhost:8123";
    }
    return window.location.protocol + "//" + window.location.hostname + ":8123";
  }
  return "http://localhost:8123";
}

export function getWsUrl() {
  if (typeof window !== 'undefined') {
    if (window.location.protocol === 'app:') {
      return "ws://localhost:8123";
    }
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return protocol + "//" + window.location.hostname + ":8123";
  }
  return "ws://localhost:8123";
}
