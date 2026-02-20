import { useState } from "react";
import companyLogo from "../assets/company-logo.svg";

type LoginProps = {
  onLogin: (userName: string, userEmail: string) => void;
};

export default function Login({ onLogin }: LoginProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function deriveUserNameFromEmail(userEmail: string): string {
    const localPart = userEmail.split("@")[0] || "user";
    return localPart
      .replace(/[._-]+/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .split(" ")
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ");
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const cleanEmail = email.trim();
    if (!cleanEmail || !password.trim()) {
      setError("Email and password are required.");
      return;
    }

    if (!cleanEmail.toLowerCase().endsWith("@zalaris.com")) {
      setError("Use your @zalaris.com email address.");
      return;
    }

    setLoading(true);
    const normalizedEmail = cleanEmail.toLowerCase();
    const userName = deriveUserNameFromEmail(normalizedEmail) || normalizedEmail;

    onLogin(userName, normalizedEmail);
    setLoading(false);
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-sky-100 via-cyan-50 to-blue-100 p-6 dark:from-slate-950 dark:via-slate-900 dark:to-slate-900 flex items-center justify-center">
      <div className="w-full max-w-md rounded-xl border border-sky-200 bg-sky-50 p-7 shadow-lg dark:border-slate-700 dark:bg-slate-900">
        <div className="mb-4 inline-flex rounded-md border border-slate-200 bg-white p-1 shadow-sm">
          <img src={companyLogo} alt="Company logo" className="h-14 w-14" />
        </div>
        <h1 className="mb-1 text-2xl font-bold text-indigo-700 dark:text-indigo-300">
          Harmonization Bot
        </h1>
        <p className="mb-6 text-sm text-gray-600 dark:text-slate-300">
          Sign in to access your governance dashboard.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-slate-300">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              placeholder="name@company.com"
              autoComplete="email"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-slate-300">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              placeholder="Enter password"
              autoComplete="current-password"
            />
          </div>

          {error && (
            <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-2 rounded-md disabled:opacity-60"
          >
            {loading ? "Signing in..." : "Login"}
          </button>
        </form>
      </div>
    </div>
  );
}
