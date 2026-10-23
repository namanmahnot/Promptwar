/**
 * Firebase Auth, loaded lazily so the sign-in SDK does not block first paint.
 * The web config is public by design; it identifies the project, it does not grant access.
 */
const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

export const firebaseEnabled = Boolean(firebaseConfig.apiKey);

let authPromise;

async function getAuthModule() {
  authPromise ??= (async () => {
    const [{ initializeApp }, authModule] = await Promise.all([import('firebase/app'), import('firebase/auth')]);
    const app = initializeApp(firebaseConfig);
    return { auth: authModule.getAuth(app), authModule };
  })();
  return authPromise;
}

export async function watchUser(callback) {
  const { auth, authModule } = await getAuthModule();
  return authModule.onAuthStateChanged(auth, callback);
}

export async function signInWithGoogle() {
  const { auth, authModule } = await getAuthModule();
  await authModule.signInWithPopup(auth, new authModule.GoogleAuthProvider());
}

export async function signOutUser() {
  const { auth, authModule } = await getAuthModule();
  await authModule.signOut(auth);
}
