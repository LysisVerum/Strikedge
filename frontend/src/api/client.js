import { SESSION_KEY } from '../context/AuthContext';

function getToken() {
  return localStorage.getItem(SESSION_KEY);
}

async function request(path, options = {}) {
  const token = getToken();
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`/api${path}`, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ description: res.statusText }));
    throw new Error(err.description ?? err.detail ?? res.statusText);
  }
  return res.json();
}

export const api = {
  health:      ()     => request('/health'),
  todayPicks:  ()     => request('/picks/today'),
  performance: ()     => request('/performance'),
  liveRecord:  ()     => request('/live-record'),
  skipped:     ()     => request('/skipped'),
  kAccuracy:   ()     => request('/k-accuracy'),
  logLines:    (body) => request('/picks/log-lines', { method: 'POST',   body: JSON.stringify(body) }),
  deleteLine:  (body) => request('/picks/log-lines', { method: 'DELETE', body: JSON.stringify(body) }),
  predict:     (body) => request('/picks/predict',   { method: 'POST',   body: JSON.stringify(body) }),
  refresh:     ()     => request('/picks/refresh',   { method: 'POST' }),

  // Hitting props
  hittingToday:       ()     => request('/hitting/today'),
  hittingPerformance: ()     => request('/hitting/performance'),
  hittingLiveRecord:  ()     => request('/hitting/live-record'),
  hittingSkipped:     ()     => request('/hitting/skipped'),
  hittingAccuracy:    ()     => request('/hitting/accuracy'),
  hittingRefresh:     ()     => request('/hitting/refresh', { method: 'POST' }),
  hittingDeleteLine:  (body) => request('/hitting/log-lines', { method: 'DELETE', body: JSON.stringify(body) }),

  // Auth
  sendMagicLink: (email)  => request('/auth/magic-link', { method: 'POST', body: JSON.stringify({ email }) }),
  me:            ()       => request('/auth/me'),
  logout:        ()       => request('/auth/logout', { method: 'POST' }),

  unlockPick: (pitcher_name) => request('/picks/unlock', { method: 'POST', body: JSON.stringify({ pitcher_name }) }),

  // Stripe
  createCheckout:      () => request('/stripe/checkout', { method: 'POST' }),
  cancelSubscription:  () => request('/stripe/cancel',   { method: 'POST' }),
};
