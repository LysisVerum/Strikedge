import { createContext, useContext, useState, useEffect, useCallback } from 'react';

const AuthContext = createContext(null);

const SESSION_KEY = 'se_session';

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(null);   // { email, tier }
  const [loading, setLoading] = useState(true);

  const loadSession = useCallback(async () => {
    const token = localStorage.getItem(SESSION_KEY);
    if (!token) { setLoading(false); return; }
    try {
      const res = await fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setUser({ ...data, token });
      } else {
        localStorage.removeItem(SESSION_KEY);
      }
    } catch {
      // network error — keep the stored token, user stays null
    }
    setLoading(false);
  }, []);

  useEffect(() => { loadSession(); }, [loadSession]);

  const login = (sessionToken, email, tier) => {
    localStorage.setItem(SESSION_KEY, sessionToken);
    setUser({ token: sessionToken, email, tier });
  };

  const logout = async () => {
    const token = localStorage.getItem(SESSION_KEY);
    if (token) {
      fetch('/api/auth/logout', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      }).catch(() => {});
    }
    localStorage.removeItem(SESSION_KEY);
    setUser(null);
  };

  const refreshUser = async () => {
    const token = localStorage.getItem(SESSION_KEY);
    if (!token) return;
    try {
      const res = await fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setUser({ ...data, token });
      }
    } catch {}
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

export { SESSION_KEY };
