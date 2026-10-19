import { useState } from "react";
import { supabase } from "../lib/supabase";

// Sign in or sign up with Supabase Auth (it stores emails and passwords safely; our
// tables never see a password). Sign-up sends the name and the browser's time zone,
// which the database copies into the user's profile.
function AuthForm() {
  const [mode, setMode] = useState("signIn");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setBusy(true);
    setMessage("");
    const { data, error } =
      mode === "signIn"
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signUp({
            email,
            password,
            options: {
              data: {
                first_name: firstName,
                last_name: lastName,
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
              },
            },
          });
    setBusy(false);
    if (error) setMessage(error.message);
    else if (mode === "signUp" && !data.session) setMessage("Check your email to confirm your account, then sign in.");
  }

  return (
    <form className="auth-form" onSubmit={handleSubmit}>
      <h2>{mode === "signIn" ? "Sign in" : "Create your account"}</h2>
      {mode === "signUp" && (
        <>
          <input value={firstName} onChange={(e) => setFirstName(e.target.value)} placeholder="First name" required />
          <input value={lastName} onChange={(e) => setLastName(e.target.value)} placeholder="Last name" required />
        </>
      )}
      <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" required />
      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Password (at least 6 characters)"
        minLength={6}
        required
      />
      <button type="submit" disabled={busy}>{mode === "signIn" ? "Sign in" : "Sign up"}</button>
      {message && <p className="auth-message">{message}</p>}
      <button type="button" className="link" onClick={() => setMode(mode === "signIn" ? "signUp" : "signIn")}>
        {mode === "signIn" ? "No account yet? Sign up" : "Already have an account? Sign in"}
      </button>
    </form>
  );
}

export default AuthForm;
