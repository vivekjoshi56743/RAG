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
    <main className="min-h-screen bg-slate-50 flex items-center justify-center p-6">
      <section className="w-full max-w-md bg-white border rounded-2xl shadow-sm p-6">
        <h1 className="text-2xl font-semibold text-slate-900">Sign in to RAG Engine</h1>
        <p className="text-sm text-slate-600 mt-1">
          Use your Google account to access documents, search, and chat.
        </p>

        <button
          onClick={onSignIn}
          disabled={loading || submitting}
          className="mt-6 w-full rounded-lg bg-blue-600 text-white px-4 py-2.5 hover:bg-blue-700 disabled:opacity-50"
        >
          {submitting ? "Signing in..." : "Continue with Google"}
        </button>

        {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
      </section>
    </main>
  );
}
