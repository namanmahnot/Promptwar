import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { firebaseEnabled, signInWithGoogle, signOutUser, watchUser } from './firebase.js';

const AuthContext = createContext(null);

// Local development without Firebase: the gateway accepts the literal token "dev"
// only when it runs with NODE_ENV=development and AUTH_DEV_BYPASS=true.
const devBypass = !firebaseEnabled && import.meta.env.VITE_AUTH_DEV_BYPASS === 'true';
const DEV_USER = { uid: 'dev-user', displayName: 'Local developer', getIdToken: async () => 'dev' };

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(firebaseEnabled);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!firebaseEnabled) return undefined;
    let unsubscribe = () => {};
    watchUser((next) => {
      setUser(next);
      setLoading(false);
    }).then((fn) => {
      unsubscribe = fn;
    });
    return () => unsubscribe();
  }, []);

  const signIn = useCallback(async () => {
    setError(null);
    if (devBypass) {
      setUser(DEV_USER);
      return;
    }
    try {
      await signInWithGoogle();
    } catch (err) {
      if (err?.code !== 'auth/popup-closed-by-user') setError('Sign-in failed. Please try again.');
    }
  }, []);

  const signOut = useCallback(async () => {
    if (firebaseEnabled) await signOutUser();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, error, signIn, signOut, configured: firebaseEnabled || devBypass }),
    [user, loading, error, signIn, signOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>');
  return context;
}
