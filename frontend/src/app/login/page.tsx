"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { user, loading, signInWithGoogle } = useAuth();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!loading && user) {
      router.replace("/chat");
    }
  }, [loading, user, router]);

  const onSignIn = async () => {
    setError(null);
    setSubmitting(true);
    try {
      await signInWithGoogle();
      router.replace("/chat");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-100 p-6">
      <section className="surface-card w-full max-w-md p-7">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Sign in to RAG Engine</h1>
        <p className="mt-1 text-sm text-slate-600">
          Use your Google account to access documents, search, and chat.
        </p>

        <button
          onClick={onSignIn}
          disabled={loading || submitting}
          className="btn-primary mt-6 w-full"
          type="button"
        >
          {submitting ? "Signing in..." : "Continue with Google"}
        </button>

        {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
      </section>
    </main>
  );
}
