import { Avatar, Box, Logo, ThemeToggle } from "../ui";
import { Gear } from "../ui/icons";

// The header bar: logo | date | theme | settings | avatar. Phones get the compact version.
function AppHeader({ profile, compact = false }) {
  const today = new Date();
  const date = today.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" }).toUpperCase().replace(",", "");
  return (
    <Box as="header" className="app-header slam">
      <Logo short={compact} />
      <span className="spacer" />
      {!compact && <span className="tag fill-blue date-tag" aria-label={`Today is ${today.toLocaleDateString([], { dateStyle: "full" })}`}>{date}</span>}
      <ThemeToggle />
      <a className="btn icon-btn surface" href="#/settings" aria-label="Settings"><Gear /></a>
      {!compact && <Avatar name={profile?.first_name} />}
    </Box>
  );
}

export default AppHeader;
