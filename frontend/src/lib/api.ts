export function getBaseUrl() {
  if (typeof window !== 'undefined') {
    return window.location.protocol + "//" + window.location.hostname + ":8000";
  }
  return "http://localhost:8000";
}

export function getWsUrl() {
  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return protocol + "//" + window.location.hostname + ":8000";
  }
  return "ws://localhost:8000";
}
