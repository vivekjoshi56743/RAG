"use client";
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  getAuth,
  onAuthStateChanged,
  signInWithPopup,
  GoogleAuthProvider,
  signOut as firebaseSignOut,
  type User as FirebaseUser,
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
  displayName?: string | null;
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
  const [firebaseUser, setFirebaseUser] = useState<FirebaseUser | null>(null);
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
      setFirebaseUser(u);
      setUser(u ? { uid: u.uid, email: u.email, displayName: u.displayName } : null);
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
      setFirebaseUser(null);
      return;
    }
    if (!auth) return;
    await firebaseSignOut(auth);
  };

  const getIdToken = async () => {
    if (devAuthEnabled) {
      return user ? devAuthToken : null;
    }
    if (!firebaseUser) {
      return null;
    }
    return firebaseUser.getIdToken();
  };

  const value = useMemo(
    () => ({ user, loading, signInWithGoogle, signOut, getIdToken }),
    [user, loading],
  );

  return (
    <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);

export function useRequireAuth() {
  const auth = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!auth.loading && !auth.user) {
      router.replace("/login");
    }
  }, [auth.loading, auth.user, router]);

  return auth;
}
