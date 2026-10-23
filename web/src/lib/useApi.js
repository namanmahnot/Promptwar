import { useMemo } from 'react';
import { createApi } from './api.js';
import { useAuth } from './auth.jsx';

export function useApi() {
  const { user } = useAuth();
  return useMemo(() => createApi(() => user.getIdToken()), [user]);
}
