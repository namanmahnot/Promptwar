import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { AnswerView } from '../components/AnswerView.jsx';
import { ProgressSteps } from '../components/ProgressSteps.jsx';
import { formatBytes, formatMs, formatPercent, formatValue } from '../lib/format.js';
import { answered, blocked } from './fixtures.js';

describe('AnswerView', () => {
  it('shows the insight, key numbers, assumptions and a data table', () => {
    render(<AnswerView result={answered} />);

    expect(screen.getByRole('heading', { level: 2, name: answered.question })).toBeInTheDocument();
    expect(screen.getByText(answered.answer.insight)).toBeInTheDocument();
    expect(screen.getByText('Highest category')).toBeInTheDocument();
    expect(screen.queryByText('Rows returned')).not.toBeInTheDocument();
    expect(screen.getByText('Counts completed items only.')).toBeInTheDocument();

    const table = screen.getByRole('table', { name: answered.question });
    expect(within(table).getAllByRole('columnheader').map((th) => th.textContent)).toEqual(['category', 'revenue']);
    expect(within(table).getAllByRole('row')).toHaveLength(3);
  });

  it('announces a blocked request with its reason and does not render data', () => {
    render(<AnswerView result={blocked} />);
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Request blocked (UNSAFE_SQL)');
    expect(alert).toHaveTextContent('users.email');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('offers example questions when the question is out of scope', async () => {
    const onExample = vi.fn();
    render(<AnswerView result={{ ...blocked, code: 'OUT_OF_SCOPE', message: 'Not about the store.' }} onExample={onExample} />);
    await userEvent.click(screen.getAllByRole('button', { name: /revenue/i })[0]);
    expect(onExample).toHaveBeenCalledOnce();
  });

  it('labels cached answers with zero cost', () => {
    render(<AnswerView result={{ ...answered, status: 'cached', cached: true, metrics: { ...answered.metrics, latencyMs: 40 } }} />);
    expect(screen.getByText(/0 AI calls, 0 bytes scanned/)).toBeInTheDocument();
    expect(screen.getByText('Cached')).toBeInTheDocument();
  });
});

describe('TracePanel', () => {
  it('lists every step with timings, the SQL and the job id', async () => {
    render(<AnswerView result={answered} />);
    await userEvent.click(screen.getByText('How this answer was produced'));

    expect(screen.getByText('Safety pre-filter')).toBeInTheDocument();
    expect(screen.getByText('Write SQL (Gemini)')).toBeInTheDocument();
    expect(screen.getByText(answered.sql)).toBeInTheDocument();
    expect(screen.getByText('job_123')).toBeInTheDocument();
    expect(screen.getByText('2.5 MB')).toBeInTheDocument();
  });

  it('copies the SQL and announces it', async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue();
    render(<AnswerView result={answered} />);
    await user.click(screen.getByText('How this answer was produced'));
    await user.click(screen.getByRole('button', { name: 'Copy SQL' }));
    expect(writeText).toHaveBeenCalledWith(answered.sql);
    expect(await screen.findByText('SQL copied to clipboard')).toBeInTheDocument();
  });
});

describe('ProgressSteps', () => {
  it('exposes the current step through a polite live region', () => {
    render(<ProgressSteps />);
    expect(screen.getByRole('status')).toHaveTextContent('Checking the question');
    expect(screen.getByRole('list', { name: 'Analysis steps' }).querySelector('[aria-current="step"]')).not.toBeNull();
  });
});

describe('format helpers', () => {
  it('formats values for people', () => {
    expect(formatValue(1234567.891)).toBe('1,234,567.89');
    expect(formatValue(null)).toBe('—');
    expect(formatBytes(2_500_000)).toBe('2.5 MB');
    expect(formatBytes(0)).toBe('0 MB');
    expect(formatMs(850)).toBe('850 ms');
    expect(formatMs(6120)).toBe('6.1 s');
    expect(formatPercent(0.85)).toBe('85.0%');
    expect(formatPercent(1)).toBe('100%');
  });
});
