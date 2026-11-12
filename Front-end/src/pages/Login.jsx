import { useState } from "react";
import { supabase } from "../lib/supabase";
import { Alert, Box, Field, Logo, Marquee, Sticker, ThemeToggle } from "../components/ui";
import { ArrowRight, Check, Eye, EyeOff, Lock } from "../components/ui/icons";

// Supabase's messages, in plain language.
export function friendlyAuthError(message = "") {
  const m = message.toLowerCase();
  if (m.includes("invalid login credentials")) return "That email and password don't match an account. Check them and try again.";
  if (m.includes("email not confirmed")) return "Confirm your email first: open the link we sent you, then log in.";
  if (m.includes("already registered")) return "There's already an account with this email. Log in instead.";
  if (m.includes("rate limit") || m.includes("too many")) return "Too many tries in a short time. Wait a minute and try again.";
  if (m.includes("failed to fetch") || m.includes("network")) return "Can't reach the sign-in service. Check your connection and try again.";
  if (m.includes("password")) return message;
  return message || "Something went wrong. Try again.";
}

function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [errorKey, setErrorKey] = useState(0); // replays the shake for a repeated error
  const [busy, setBusy] = useState(false);

  function fail(message) {
    setError(message);
    setErrorKey((k) => k + 1);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!email.trim() || !password) {
      fail("Enter your email and password to log in.");
      return;
    }
    setBusy(true);
    setError("");
    // Same sign-in as before (AuthForm): Supabase keeps the session, and the app moves to Home.
    const { error: authError } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
    setBusy(false);
    if (authError) fail(friendlyAuthError(authError.message));
  }

  return (
    <div className="page">
      <header className="box topbar slam">
        <Logo />
        <span className="spacer" />
        <ThemeToggle />
      </header>

      <main className="auth-cols">
        <Box className="auth-form-card slam slam-1" aria-labelledby="login-title">
          <span className="tag fill-purple kicker">Log in</span>
          <h1 id="login-title" className="hero-title">Welcome back.</h1>
          <p className="lede">Pick up where you left off. Your daily overview is waiting for you.</p>

          <form onSubmit={handleSubmit} noValidate>
            {error && <Alert key={errorKey}>{error}</Alert>}
            <Field label="Email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            <div className="field">
              <label htmlFor="login-password">Password</label>
              <div className="inp-wrap">
                <input
                  id="login-password"
                  className="inp"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button
                  type="button"
                  className="eye"
                  onClick={() => setShowPassword((s) => !s)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword}
                >
                  {showPassword ? <EyeOff width={22} height={22} /> : <Eye width={22} height={22} />}
                </button>
              </div>
            </div>
            <button type="submit" className="btn big full" disabled={busy}>
              {busy ? "Logging in…" : <>Log in <ArrowRight width={20} height={20} /></>}
            </button>
          </form>

          <hr className="divider" />
          <div className="signup-cta">
            <p>New to Steady Planner?</p>
            <a className="btn pink" href="#/signup">Create an account</a>
          </div>
        </Box>

        <Box className="promo fill-blue slam slam-2" aria-labelledby="promo-title">
          <Sticker ring="NOTHING CHANGES UNTIL YOU SAY YES · NOTHING CHANGES UNTIL YOU SAY YES ·" color="yellow">
            You decide
          </Sticker>
          <h2 id="promo-title">
            The planner that plans <span className="tilt-chip">with</span> you.
          </h2>
          <p>
            Steady looks at your calendar, tasks and journal, then suggests a better day. You approve every change.
          </p>
          <div className="sample-card" aria-hidden="true">
            <span className="tag fill-blue">Calendar</span>
            <strong>Move "Study session"</strong>
            <span className="mono">6:00–8:00 PM → 8:00–10:00 PM</span>
            <span className="muted">Frees your evening for the gym.</span>
            <div className="row">
              <span className="btn small green"><Check width={16} height={16} /> Accept</span>
              <span className="btn small surface">Decline</span>
            </div>
          </div>
          <p className="note" style={{ color: "var(--on)" }}>
            <Lock /> Your calendar, tasks and journal are visible only to you.
          </p>
          <Marquee size="small" items={["Calendar", "Tasks", "Journal", "Daily AI overview", "Suggestions you approve"]} />
        </Box>
      </main>
    </div>
  );
}

export default Login;
