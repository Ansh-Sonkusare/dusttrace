import type { Metadata } from "next";
import "@fontsource/manrope/300.css";
import "@fontsource/manrope/400.css";
import "@fontsource/manrope/500.css";
import "@fontsource/manrope/600.css";
import "@fontsource/manrope/700.css";
import "./globals.css";
import Nav from "@/components/Nav";
import Logo from "@/components/Logo";

export const metadata: Metadata = {
  title: "DustTrace",
  description: "Forecast, prevent and prove construction dust in Mumbai wards.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
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
      </body>
    </html>
  );
}
