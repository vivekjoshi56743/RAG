"use client";

import { ThemeProvider } from "next-themes";
import { Toaster } from "react-hot-toast";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <Toaster 
        position="top-center" 
        toastOptions={{
          className: "dark:bg-slate-800 dark:text-slate-100 dark:border dark:border-slate-700",
          style: {
            borderRadius: '12px',
          }
        }} 
      />
      {children}
    </ThemeProvider>
  );
}
