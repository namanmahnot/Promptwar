import { useEffect, useRef } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../lib/auth.jsx';

const NAV = [
  { to: '/', label: 'Ask', end: true },
  { to: '/history', label: 'History' },
  { to: '/metrics', label: 'Metrics' },
];

export function Layout() {
  const { user, signOut } = useAuth();
  const mainRef = useRef(null);
  const { pathname } = useLocation();
  const firstRender = useRef(true);

  // Move focus to the new page on client-side navigation, as a full page load would.
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    mainRef.current?.focus();
  }, [pathname]);

  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-white focus:px-4 focus:py-2 focus:font-semibold focus:text-indigo-800 focus:shadow"
      >
        Skip to main content
      </a>
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <p className="text-lg font-bold text-indigo-800">
            InsightPilot <span className="sr-only">— verified business answers</span>
          </p>
          <nav aria-label="Main">
            <ul className="flex gap-1">
              {NAV.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.end}
                    className={({ isActive }) =>
                      `inline-flex min-h-11 items-center rounded-md px-3 text-sm font-medium ${
                        isActive ? 'bg-indigo-50 text-indigo-800 underline underline-offset-4' : 'text-slate-700 hover:bg-slate-100'
                      }`
                    }
                  >
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
          <div className="flex items-center gap-3 text-sm">
            <span className="hidden text-slate-700 sm:inline">{user?.displayName ?? user?.email}</span>
            <button
              type="button"
              onClick={signOut}
              className="min-h-11 rounded-md border border-slate-300 px-3 font-medium text-slate-800 hover:bg-slate-50"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main id="main" ref={mainRef} tabIndex={-1} className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 focus:outline-none">
        <Outlet />
      </main>
      <footer className="border-t border-slate-200 bg-white py-4 text-center text-xs text-slate-700">
        Data: BigQuery public dataset <code>thelook_ecommerce</code> (synthetic). Read-only, cost-capped at 1 GB per query.
      </footer>
    </div>
  );
}
