import Nav from "@/components/Nav";
import Logo from "@/components/Logo";

// The ward console: left rail with navigation. Everything under (console) sits behind the password.
export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="app">
      <aside className="rail" aria-label="Main navigation">
        <div className="mark">
          <Logo />
          <div>
            <b>DustTrace</b>
            <small>Ward console</small>
          </div>
        </div>
        <Nav />
        <div className="grow" />
        <div className="foot">Team ARA IGNITE<br />InnovateX 2026–27</div>
      </aside>
      <div style={{ minWidth: 0 }}>{children}</div>
    </div>
  );
}
