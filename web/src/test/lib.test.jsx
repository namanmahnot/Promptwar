import { act, render, renderHook, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, createApi } from '../lib/api.js';

describe('API client', () => {
  const fetchMock = vi.fn();
  beforeEach(() => vi.stubGlobal('fetch', fetchMock));
  afterEach(() => {
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

  const reply = (status, body) => Promise.resolve(new Response(JSON.stringify(body), { status }));

  it('sends the ID token and JSON body to the same origin', async () => {
    fetchMock.mockReturnValue(reply(200, { status: 'answered' }));
    const api = createApi(async () => 'tok');
    await api.ask('Revenue by month');

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/ask');
    expect(init.method).toBe('POST');
    expect(init.headers.Authorization).toBe('Bearer tok');
    expect(JSON.parse(init.body)).toEqual({ question: 'Revenue by month' });
  });

  it('returns blocked and failed results instead of throwing', async () => {
    fetchMock.mockReturnValue(reply(422, { status: 'blocked', code: 'UNSAFE_SQL' }));
    const result = await createApi(async () => 't').ask('Show emails');
    expect(result.code).toBe('UNSAFE_SQL');
  });

  it('throws ApiError with the server code for other errors', async () => {
    fetchMock.mockReturnValue(reply(429, { status: 'error', code: 'RATE_LIMITED', message: 'Slow down', requestId: 'r1' }));
    const error = await createApi(async () => 't').history().catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect([error.status, error.code, error.message, error.requestId]).toEqual([429, 'RATE_LIMITED', 'Slow down', 'r1']);
  });

  it('maps network failures to a friendly message and passes aborts through', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    const network = await createApi(async () => 't').evalLatest().catch((e) => e);
    expect(network.code).toBe('NETWORK');

    fetchMock.mockRejectedValueOnce(Object.assign(new Error('aborted'), { name: 'AbortError' }));
    const aborted = await createApi(async () => 't').ask('q').catch((e) => e);
    expect(aborted.name).toBe('AbortError');
  });

  it('handles non-JSON error bodies', async () => {
    fetchMock.mockReturnValue(Promise.resolve(new Response('oops', { status: 500 })));
    const error = await createApi(async () => 't').history().catch((e) => e);
    expect([error.status, error.code]).toEqual([500, 'UNKNOWN']);
  });
});

describe('AuthProvider with Firebase', () => {
  let authCallback;
  const firebase = {
    firebaseEnabled: true,
    watchUser: vi.fn(async (callback) => {
      authCallback = callback;
      return () => {};
    }),
    signInWithGoogle: vi.fn(async () => {}),
    signOutUser: vi.fn(async () => {}),
  };

  beforeEach(() => {
    vi.resetModules();
    vi.doMock('../lib/firebase.js', () => firebase);
  });
  afterEach(() => vi.doUnmock('../lib/firebase.js'));

  async function setup() {
    const { AuthProvider, useAuth } = await import('../lib/auth.jsx');
    function Probe() {
      const { user, loading, error, signIn, signOut } = useAuth();
      if (loading) return <p>loading</p>;
      return (
        <>
          <p>{user ? `hi ${user.displayName}` : 'signed out'}</p>
          {error && <p role="alert">{error}</p>}
          <button type="button" onClick={signIn}>in</button>
          <button type="button" onClick={signOut}>out</button>
        </>
      );
    }
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
  }

  it('tracks the Firebase user and signs in and out', async () => {
    await setup();
    expect(screen.getByText('loading')).toBeInTheDocument();
    await waitFor(() => expect(authCallback).toBeTypeOf('function'));
    act(() => authCallback({ displayName: 'Ada' }));
    expect(screen.getByText('hi Ada')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'in' }));
    expect(firebase.signInWithGoogle).toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'out' }));
    expect(firebase.signOutUser).toHaveBeenCalled();
    expect(screen.getByText('signed out')).toBeInTheDocument();
  });

  it('shows an error when sign-in fails, but not when the popup is closed', async () => {
    await setup();
    await waitFor(() => expect(authCallback).toBeTypeOf('function'));
    act(() => authCallback(null));

    firebase.signInWithGoogle.mockRejectedValueOnce({ code: 'auth/popup-closed-by-user' });
    await userEvent.click(screen.getByRole('button', { name: 'in' }));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();

    firebase.signInWithGoogle.mockRejectedValueOnce({ code: 'auth/network-request-failed' });
    await userEvent.click(screen.getByRole('button', { name: 'in' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Sign-in failed');
  });

  it('useAuth outside the provider is a programming error', async () => {
    const { useAuth } = await import('../lib/auth.jsx');
    vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => renderHook(() => useAuth())).toThrow('useAuth must be used inside <AuthProvider>');
  });
});

describe('firebase wrapper', () => {
  beforeEach(() => vi.resetModules());

  it('initialises Firebase lazily and delegates to the SDK', async () => {
    const authModule = {
      getAuth: vi.fn(() => 'auth'),
      onAuthStateChanged: vi.fn(() => 'unsubscribe'),
      signInWithPopup: vi.fn(async () => {}),
      signOut: vi.fn(async () => {}),
      GoogleAuthProvider: class {},
    };
    const initializeApp = vi.fn(() => 'app');
    vi.doMock('firebase/app', () => ({ initializeApp }));
    vi.doMock('firebase/auth', () => authModule);

    const fb = await import('../lib/firebase.js');
    expect(await fb.watchUser(() => {})).toBe('unsubscribe');
    await fb.signInWithGoogle();
    await fb.signOutUser();

    expect(initializeApp).toHaveBeenCalledTimes(1);
    expect(authModule.signInWithPopup).toHaveBeenCalledWith('auth', expect.any(authModule.GoogleAuthProvider));
    expect(authModule.signOut).toHaveBeenCalledWith('auth');
  });
});
