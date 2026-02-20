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
    <div className="hb-login-page">
      <div className="hb-login-glow" />
      <div className="hb-login-card">
        <div className="hb-login-logo">
          <img src={companyLogo} alt="Company logo" className="h-14 w-14" />
        </div>
        <h1 className="hb-login-title">
          Harmonization Bot
        </h1>
        <p className="hb-login-subtitle">
          Sign in to access your governance dashboard.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="hb-login-label">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="hb-login-input"
              placeholder="name@company.com"
              autoComplete="email"
            />
          </div>

          <div>
            <label className="hb-login-label">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="hb-login-input"
              placeholder="Enter password"
              autoComplete="current-password"
            />
          </div>

          {error && (
            <div className="hb-login-error">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="hb-login-submit"
          >
            {loading ? "Signing in..." : "Login"}
          </button>
        </form>
      </div>
    </div>
  );
}
