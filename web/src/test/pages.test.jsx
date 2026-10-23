import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { answered, blocked } from './fixtures.js';

const api = {
  ask: vi.fn(),
  history: vi.fn(),
  evalLatest: vi.fn(),
};
vi.mock('../lib/useApi.js', () => ({ useApi: () => api }));

const auth = { user: { uid: 'u1', displayName: 'Ada' }, loading: false, error: null, configured: true, signIn: vi.fn(), signOut: vi.fn() };
vi.mock('../lib/auth.jsx', () => ({ useAuth: () => auth }));

const { AppRoutes } = await import('../App.jsx');

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

async function expectNoAxeViolations(container) {
  // jsdom cannot compute colours, so contrast is verified manually against Tailwind's palette.
  const results = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } });
  expect(results.violations.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
}

beforeEach(() => {
  vi.resetAllMocks();
  auth.user = { uid: 'u1', displayName: 'Ada' };
  api.history.mockResolvedValue({ items: [] });
  api.evalLatest.mockResolvedValue({ run: null });
});

describe('Ask page', () => {
  it('asks on Enter, shows the answer and moves focus to it', async () => {
    api.ask.mockResolvedValue(answered);
    renderAt('/');

    await userEvent.type(screen.getByLabelText('Your question'), 'Top categories by revenue{Enter}');

    expect(api.ask).toHaveBeenCalledWith('Top categories by revenue', expect.any(AbortSignal));
    const heading = await screen.findByRole('heading', { level: 2, name: answered.question });
    await waitFor(() => expect(heading).toHaveFocus());
  });

  it('asks an example question with one click', async () => {
    api.ask.mockResolvedValue(answered);
    renderAt('/');
    await userEvent.click(screen.getByRole('button', { name: /Top 5 product categories/ }));
    expect(api.ask).toHaveBeenCalledWith('Top 5 product categories by revenue in the last 90 days', expect.any(AbortSignal));
  });

  it('validates short questions without calling the API', async () => {
    renderAt('/');
    await userEvent.type(screen.getByLabelText('Your question'), 'hi{Enter}');
    expect(screen.getByRole('alert')).toHaveTextContent('at least 3 characters');
    expect(screen.getByLabelText('Your question')).toHaveAttribute('aria-invalid', 'true');
    expect(api.ask).not.toHaveBeenCalled();
  });

  it('shows network errors in an alert', async () => {
    api.ask.mockRejectedValue(new Error('Cannot reach the server.'));
    renderAt('/');
    await userEvent.type(screen.getByLabelText('Your question'), 'Revenue by month{Enter}');
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the server.');
  });

  it('has no accessibility violations, empty or with an answer', async () => {
    api.ask.mockResolvedValue(answered);
    const { container } = renderAt('/');
    await expectNoAxeViolations(container);
    await userEvent.type(screen.getByLabelText('Your question'), 'Top categories{Enter}');
    await screen.findByRole('heading', { level: 2, name: answered.question });
    await expectNoAxeViolations(container);
  });

  it('has no accessibility violations for a blocked answer', async () => {
    api.ask.mockResolvedValue(blocked);
    const { container } = renderAt('/');
    await userEvent.type(screen.getByLabelText('Your question'), 'Show customer emails{Enter}');
    await screen.findByRole('alert');
    await expectNoAxeViolations(container);
  });
});

describe('navigation and layout', () => {
  it('has a skip link, labelled navigation and marks the current page', () => {
    renderAt('/metrics');
    expect(screen.getByRole('link', { name: 'Skip to main content' })).toHaveAttribute('href', '#main');
    const nav = screen.getByRole('navigation', { name: 'Main' });
    expect(nav).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Metrics' })).toHaveAttribute('aria-current', 'page');
  });

  it('shows the sign-in page when signed out', async () => {
    auth.user = null;
    const { container } = renderAt('/');
    expect(screen.getByRole('button', { name: 'Sign in with Google' })).toBeEnabled();
    await expectNoAxeViolations(container);
  });
});

describe('History page', () => {
  it('lists my past questions with their status', async () => {
    api.history.mockResolvedValue({
      items: [{ queryId: 'abc', question: 'Revenue by month', status: 'answered', latencyMs: 5000, createdAt: '2026-10-23T10:00:00Z' }],
    });
    const { container } = renderAt('/history');
    expect(await screen.findByText('Revenue by month')).toBeInTheDocument();
    expect(screen.getByText('Answered')).toBeInTheDocument();
    await expectNoAxeViolations(container);
  });
});

describe('Metrics page', () => {
  it('shows the latest eval run accessibly', async () => {
    api.evalLatest.mockResolvedValue({
      run: {
        startedAt: '2026-10-23T10:00:00Z',
        model: 'gemini-3.5-flash',
        promptVersion: 'v1',
        executionAccuracy: 0.85,
        attackBlockRate: 1,
        validSqlRate: 0.95,
        groundingViolations: 0,
        p50Ms: 6100,
        p95Ms: 11000,
        medianBytes: 4_000_000,
        meanLlmCalls: 2.1,
        results: [{ qid: 'G01', question: 'Top 5 categories', pass: true, ms: 6000, sql: 'SELECT 1' }],
      },
    });
    const { container } = renderAt('/metrics');

    expect(await screen.findByText('85.0%')).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(screen.getByRole('rowheader', { name: 'G01' })).toBeInTheDocument();
    await expectNoAxeViolations(container);
  });
});
