"use client";
import { createContext, useContext, useEffect, useState } from "react";
import {
  getAuth,
  onAuthStateChanged,
  signInWithPopup,
  GoogleAuthProvider,
  signOut as firebaseSignOut,
} from "firebase/auth";
import { initializeApp, getApps } from "firebase/app";

const devAuthEnabled = process.env.NEXT_PUBLIC_DEV_AUTH === "true";
const devAuthToken = process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN ?? "local-dev-token";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
};

if (!devAuthEnabled && !getApps().length) {
  initializeApp(firebaseConfig);
}

interface AuthUser {
  uid: string;
  email: string | null;
}

interface AuthContext {
  user: AuthUser | null;
  loading: boolean;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
  getIdToken: () => Promise<string | null>;
}

const AuthCtx = createContext<AuthContext>({
  user: null,
  loading: true,
  signInWithGoogle: async () => {},
  signOut: async () => {},
  getIdToken: async () => null,
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const auth = devAuthEnabled ? null : getAuth();

  useEffect(() => {
    if (devAuthEnabled) {
      setUser({ uid: "local-dev-user", email: "local@example.com" });
      setLoading(false);
      return;
    }
    if (!auth) return;
    return onAuthStateChanged(auth, (u) => {
      setUser(u ? { uid: u.uid, email: u.email } : null);
      setLoading(false);
    });
  }, [auth]);

  const signInWithGoogle = async () => {
    if (devAuthEnabled) {
      setUser({ uid: "local-dev-user", email: "local@example.com" });
      return;
    }
    if (!auth) return;
    const provider = new GoogleAuthProvider();
    await signInWithPopup(auth, provider);
  };

  const signOut = async () => {
    if (devAuthEnabled) {
      setUser(null);
      return;
    }
    if (!auth) return;
    await firebaseSignOut(auth);
  };

  const getIdToken = async () => {
    return user ? devAuthToken : null;
  };

  return (
    <AuthCtx.Provider value={{ user, loading, signInWithGoogle, signOut, getIdToken }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);
