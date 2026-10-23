import { BrowserRouter, Link, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout.jsx';
import { useAuth } from './lib/auth.jsx';
import { Ask } from './pages/Ask.jsx';
import { History } from './pages/History.jsx';
import { Metrics } from './pages/Metrics.jsx';
import { SignIn } from './pages/SignIn.jsx';

function NotFound() {
  return (
    <>
      <h1 className="text-2xl font-bold text-slate-900">Page not found</h1>
      <p className="mt-2">
        <Link to="/" className="font-medium text-indigo-800 underline">
          Go to Ask
        </Link>
      </p>
    </>
  );
}

export function AppRoutes() {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <p role="status" className="p-8 text-slate-700">
        Loading…
      </p>
    );
  }
  if (!user) return <SignIn />;
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Ask />} />
        <Route path="history" element={<History />} />
        <Route path="metrics" element={<Metrics />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
