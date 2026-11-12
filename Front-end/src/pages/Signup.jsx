import { useState } from "react";
import { supabase } from "../lib/supabase";
import { PRIORITY_OPTIONS, applyOnboarding, savePending } from "../lib/onboarding";
import { go } from "../lib/route";
import { Alert, Box, Field, Logo, ProgressBar, ThemeToggle } from "../components/ui";
import { ArrowLeft, ArrowRight, Check, Eye, EyeOff, Lock } from "../components/ui/icons";
import { CommitmentForm, CommitmentRow, DETECTED_ZONE, PriorityPicker, TimezoneSelect, WorkTimeChoice } from "../components/profile";
import { friendlyAuthError } from "./Login";

// Sign-up / onboarding: four steps on one page. The account is created at the end (the same Supabase
// sign-up as before, with the name and time zone the database copies into the profile), then the rest
// is saved to the profile and the calendar (lib/onboarding.js).

const STEPS = ["Account", "Hobbies & priorities", "Work style", "Fixed commitments"];
const MIN_PASSWORD = 6; // Supabase's minimum, as before

function strength(pw) {
  if (pw.length < MIN_PASSWORD) return { level: 0, label: "Too short" };
  let points = 0;
  if (pw.length >= 8) points += 1;
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) points += 1;
  if (/\d/.test(pw)) points += 1;
  if (/[^A-Za-z0-9]/.test(pw)) points += 1;
  const level = Math.max(1, points);
  return { level, label: ["Too short", "Weak", "Okay", "Good", "Strong"][level] };
}

const validEmail = (e) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e.trim());

function Signup() {
  const [step, setStep] = useState(0);
  const [account, setAccount] = useState({ first: "", last: "", email: "", password: "" });
  const [showPassword, setShowPassword] = useState(false);
  const [priorities, setPriorities] = useState([]);
  const [workTime, setWorkTime] = useState("Night");
  const [motivation, setMotivation] = useState("");
  const [timezone, setTimezone] = useState(DETECTED_ZONE);
  const [commitments, setCommitments] = useState([]);
  const [error, setError] = useState("");
  const [errorKey, setErrorKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [waitingForEmail, setWaitingForEmail] = useState(false);

  const accountValid = account.first.trim() && validEmail(account.email) && account.password.length >= MIN_PASSWORD;
  const stepValid = [Boolean(accountValid), true, true, true];
  const reachable = (i) => stepValid.slice(0, i).every(Boolean);
  const pw = strength(account.password);

  function fail(message) {
    setError(message);
    setErrorKey((k) => k + 1);
  }

  function next() {
    if (step === 0 && !accountValid) {
      if (!account.first.trim()) return fail("Enter your first name.");
      if (!validEmail(account.email)) return fail("Enter a valid email address.");
      return fail(`Use at least ${MIN_PASSWORD} characters for your password.`);
    }
    setError("");
    setStep((s) => s + 1);
  }

  async function finish() {
    setBusy(true);
    setError("");
    const email = account.email.trim();
    // The same sign-up as before: the name and time zone go along, and the database makes the profile.
    const { data, error: authError } = await supabase.auth.signUp({
      email,
      password: account.password,
      options: {
        emailRedirectTo: window.location.origin + import.meta.env.BASE_URL,
        data: { first_name: account.first.trim(), last_name: account.last.trim(), timezone },
      },
    });
    if (authError) {
      setBusy(false);
      setStep(0);
      return fail(friendlyAuthError(authError.message));
    }
    const onboarding = { priorities, workTime, motivation, timezone, commitments };
    if (data.session) {
      try {
        await applyOnboarding(data.user.id, onboarding);
      } catch (err) {
        // The account exists; what didn't save can be filled in from Settings.
        console.error("Couldn't save the onboarding answers:", err);
      }
      setBusy(false);
      go("home");
    } else {
      savePending(email, onboarding); // saved at the first log-in, after the email is confirmed
      setBusy(false);
      setWaitingForEmail(true);
    }
  }

  if (waitingForEmail) {
    return (
      <div className="page">
        <header className="box topbar slam">
          <Logo />
          <span className="spacer" />
          <ThemeToggle />
        </header>
        <Box className="signup-main slam slam-1" as="main">
          <span className="tag fill-green kicker" style={{ alignSelf: "flex-start" }}>Almost there</span>
          <h1>Check your email.</h1>
          <p className="lede">
            We sent a confirmation link to {account.email.trim()}. Open it, then log in: your answers are saved in this
            browser and go into your planner the first time you log in.
          </p>
          <a className="btn big" href="#/login" style={{ alignSelf: "flex-start" }}>Go to log in <ArrowRight width={20} height={20} /></a>
        </Box>
      </div>
    );
  }

  const pane = [
    {
      kicker: "Account",
      title: "Let's set you up.",
      lede: "Start with the basics. You can change all of this later in Settings.",
      body: (
        <>
          <div className="row2">
            <Field label="First name" autoComplete="given-name" value={account.first}
              onChange={(e) => setAccount({ ...account, first: e.target.value })} required />
            <Field label="Last name" autoComplete="family-name" value={account.last}
              onChange={(e) => setAccount({ ...account, last: e.target.value })} />
          </div>
          <Field label="Email" type="email" autoComplete="email" value={account.email}
            onChange={(e) => setAccount({ ...account, email: e.target.value })} required />
          <div className="field">
            <label htmlFor="signup-password">Password</label>
            <div className="inp-wrap">
              <input id="signup-password" className="inp" type={showPassword ? "text" : "password"} autoComplete="new-password"
                value={account.password} onChange={(e) => setAccount({ ...account, password: e.target.value })}
                aria-describedby="pw-strength pw-hint" />
              <button type="button" className="eye" onClick={() => setShowPassword((s) => !s)} aria-pressed={showPassword}
                aria-label={showPassword ? "Hide password" : "Show password"}>
                {showPassword ? <EyeOff width={22} height={22} /> : <Eye width={22} height={22} />}
              </button>
            </div>
            <div className="strength" id="pw-strength">
              <div className="strength-bars" aria-hidden="true">
                {[1, 2, 3, 4].map((n) => <span key={n} className={`${n <= pw.level ? "on" : ""} lv${pw.level}`} />)}
              </div>
              <span className="strength-label">Strength: {account.password ? pw.label : "—"}</span>
            </div>
            <p className="hint" id="pw-hint">Use 8+ characters with a capital letter, a number and a symbol (at least {MIN_PASSWORD} to sign up).</p>
          </div>
        </>
      ),
      why: (
        <>
          <h2>Your account, kept safe</h2>
          <p>Sign-in is handled by Supabase Auth, so your password is never stored in Steady's own database.</p>
          <div className="why-card">You can change your name, email and everything else in Settings.</div>
        </>
      ),
    },
    {
      kicker: "Hobbies & priorities",
      title: "What matters to you?",
      lede: "Tap your hobbies and priorities in order of importance. Your first tap is your top priority. Tap again to remove.",
      body: <PriorityPicker options={PRIORITY_OPTIONS} value={priorities} onChange={setPriorities} />,
      why: (
        <>
          <h2>Why the order matters</h2>
          <p>When two things compete for the same evening, Steady suggests the one you ranked higher first.</p>
          <div className="why-card">
            <span className="mono">#1 {priorities[0] ?? "Studying"}</span>
            gets your best focus hours.
          </div>
        </>
      ),
    },
    {
      kicker: "Work style",
      title: "How do you like to work?",
      lede: "This is a preference, not a rule. Steady tries to follow it but won't treat it as fixed.",
      body: (
        <>
          <WorkTimeChoice value={workTime} onChange={setWorkTime} />
          <Field label="What motivates you to study?" as="textarea" value={motivation} maxLength={1000}
            onChange={(e) => setMotivation(e.target.value)} placeholder="e.g. Getting into grad school. I focus better with music." />
          <TimezoneSelect value={timezone} onChange={setTimezone} />
        </>
      ),
      why: (
        <>
          <h2>Preference vs. rule</h2>
          <div className="why-card blue">
            <span className="tag fill-surface" style={{ alignSelf: "flex-start" }}>Preference</span>
            "I prefer studying at night." <span>Steady tries to fit this.</span>
          </div>
          <div className="why-card striped">
            <span className="on-chip"><Lock label="Fixed" width={14} height={14} /> Hard constraint</span>
            <span className="on-chip">"I have class 10 AM–12 PM."</span>
            <span className="on-chip">Steady must respect this.</span>
          </div>
          <p>Your timezone makes sure "midnight" means your midnight, so your daily overview matches your day.</p>
        </>
      ),
    },
    {
      kicker: "Fixed commitments",
      title: "What can't move?",
      lede: "Add classes, exams, work shifts and appointments. Steady will never suggest moving these.",
      body: (
        <>
          {commitments.length === 0 ? (
            <p className="hint">No fixed commitments yet. You can add them later in Settings.</p>
          ) : (
            <ul className="constraint-list">
              {commitments.map((c, i) => (
                <CommitmentRow key={`${c.name}-${i}`} commitment={c}
                  onRemove={() => setCommitments((all) => all.filter((_, j) => j !== i))} />
              ))}
            </ul>
          )}
          <CommitmentForm onAdd={(c) => setCommitments((all) => [...all, c])} />
        </>
      ),
      why: (
        <>
          <h2>Locked means locked</h2>
          <div className="why-card striped">
            <span className="on-chip"><Lock label="Fixed" width={14} height={14} /> CSE 232 lecture</span>
            <span className="on-chip mono">Mon, Wed, Fri · 10:00 AM</span>
          </div>
          <p>Steady never suggests moving these. You can still edit or remove them yourself any time.</p>
        </>
      ),
    },
  ][step];

  return (
    <div className="page">
      <header className="box topbar slam">
        <Logo />
        <span className="spacer" />
        <a className="btn surface" href="#/login">I have an account · Log in</a>
        <ThemeToggle />
      </header>

      <nav className="box stepper slam slam-1" aria-label="Sign-up steps">
        <ol className="steps">
          {STEPS.map((name, i) => (
            <li key={name}>
              <button type="button" className="step-btn" aria-current={i === step ? "step" : undefined}
                disabled={!reachable(i)} onClick={() => setStep(i)} aria-label={`Step ${i + 1}: ${name}`}>
                <span className={`step-num ${i < step && stepValid[i] ? "done" : ""}`}>
                  {i < step && stepValid[i] ? <Check /> : i + 1}
                </span>
                <span className="label">{name}</span>
              </button>
            </li>
          ))}
        </ol>
        <ProgressBar value={step + 1} max={4} label={`Step ${step + 1} of 4`} />
      </nav>

      <div className="signup-cols">
        <Box as="main" className="signup-main slam slam-2" aria-labelledby="step-title">
          <div className="step-pane" key={step}>
            <span className="tag fill-purple kicker" style={{ alignSelf: "flex-start" }}>
              Step {step + 1} of 4 · {pane.kicker}
            </span>
            <h1 id="step-title">{pane.title}</h1>
            <p className="lede">{pane.lede}</p>
            {error && <Alert key={errorKey}>{error}</Alert>}
            {pane.body}
          </div>
          <div className="step-nav">
            {step > 0 ? (
              <button type="button" className="btn surface" onClick={() => setStep((s) => s - 1)}>
                <ArrowLeft width={18} height={18} /> Back
              </button>
            ) : (
              <span />
            )}
            {step < 3 ? (
              <button type="button" className="btn" onClick={next}>
                Next: {STEPS[step + 1]} <ArrowRight width={18} height={18} />
              </button>
            ) : (
              <button type="button" className="btn green" onClick={finish} disabled={busy || !accountValid}>
                {busy ? "Creating your planner…" : <>Create my planner <ArrowRight width={18} height={18} /></>}
              </button>
            )}
          </div>
        </Box>
        <Box as="aside" className="why fill-purple slam slam-3" aria-label="Why we ask">
          <span className="tag fill-surface" style={{ alignSelf: "flex-start" }}>Why we ask</span>
          {pane.why}
        </Box>
      </div>
    </div>
  );
}

export default Signup;
